# RDA-060 — Auditoria e Correção da Aquisição de Documentos

**Data:** 2026-08-27
**Commit base:** `8d9651c` (RDA-059)
**Ambiente:** downloader real contra URLs de documentos que falharam no E2E do RDA-059.

---

## 1. Contexto

No E2E do RDA-059, **11/11 documentos selecionados pelo pipeline falharam no download**, resultando em **0 chunks** no corpus. Este ticket audita a causa raiz da falha de aquisição e implementa a correção viável.

O problema se manifesta em três classes de falha:
- **HTML anti-bot/challenge** — páginas baixadas com sucesso, mas sem texto útil (apenas desafios JS).
- **HTTP 403 (paywall)** — acesso negado pelo servidor.
- **PDF com Content-Type errado** (`application/octet-stream`) — PDF real servido com tipo genérico, rejeitado pelo validador. **Corrigível.**

---

## 2. FASE 1 — Inspeção do pipeline

| Componente | Comportamento |
|---|---|
| `DocumentDownloader` | Permite `text/html` e `application/octet-stream` no download |
| `FileValidator` (storage) | Só aceita `application/pdf` (checagem por header) |
| `PDFExtractor` | Só processa PDFs |
| OpenAlex provider | Prefere `best_oa_location.pdf_url` → `open_access.oa_url` (corrigido no RDA-056) |
| `WorkflowServices.process` | Retorna `ProcessResult` com `reason` em falha (RDA-058) |

**Gap identificado:** o downloader baixa o arquivo, mas o `FileValidator` rejeita PDFs servidos com Content-Type genérico (`application/octet-stream`), mesmo quando os bytes são um PDF válido. Isso derruba documentos que seriam perfeitamente processáveis.

---

## 3. FASE 2-3 — Auditoria de downloadability e classificação

Criado `backend/scripts/evaluation/run_downloadability_audit.py`, que testa o `DocumentDownloader` real contra 10 URLs de documentos que falharam no E2E do RDA-059. Resultado bruto em `downloadability_audit_20260827T183527Z.json`:

| URL | Status | Content-Type | Tamanho |
|---|---|---|---|
| bmchealthservres.../counter/pdf/... | success | text/html | 3038 |
| sciencedirect.../pdf | **failed** | HTTP 403 | — |
| pure.manchester.ac.uk/.../PRE-PEER-REVIEW.PDF | success | **application/octet-stream** | 1148559 |
| doi.org/10.1016/j.tourman.2009.02.016 | success | text/html | 2670 |
| systematicreviewsjournal.../track/pdf/... | success | text/html | 3038 |
| systematicreviewsjournal.../counter/pdf/... | success | text/html | 3038 |
| doi.org/10.14778/1453856.1453956 | **failed** | HTTP 403 | — |
| jclinepi.com/.../pdf | **failed** | HTTP 403 | — |
| doi.org/10.1016/j.wpi.2012.10.005 | success | text/html | 2695 |
| doi.org/10.1016/j.envres.2017.05.040 | success | text/html | 2732 |

### Inspeção do conteúdo HTML
`inspect_html.py` confirmou que as páginas HTML baixadas contêm **apenas desafios JS anti-bot** (Cloudflare/redirect), sem texto de artigo. A extração de HTML **não é viável**.

### Inspeção do octet-stream
`inspect_octet.py` confirmou que a URL `pure.manchester.ac.uk/.../PRE-PEER-REVIEW.PDF` é um **PDF real de 1.1 MB** (magic bytes `%PDF-1.4`) servido com Content-Type `application/octet-stream`.

### Classificação final (`classify_failures.py`)
| Classe | Qtd | Corrigível? |
|---|---|---|
| `http_error` (403/paywall) | 3 | Não |
| `html_challenge` / `html_with_text` (sem conteúdo útil) | 6 | Não |
| `pdf_wrong_type` (octet-stream) | 1 | **Sim** |

**Conclusão:** a única falha programaticamente corrigível é o PDF servido com Content-Type errado. As demais (403 e HTML anti-bot) são barreiras do servidor de origem e não podem ser resolvidas no cliente.

---

## 4. FASE 4 — Solução implementada

**Magic-byte sniffing no `FileValidator`** (`backend/app/services/storage/validator.py`):

- Adicionada a constante `_PDF_MAGIC = b"%PDF-"`.
- `_validate_content_type(self, content_type)` → `_validate_content_type(self, content, content_type)`.
- A validação agora aceita o arquivo se o Content-Type for permitido **ou** se os bytes começarem com o magic de PDF (`%PDF-`), independentemente do header.
- `validate()` atualizado para passar `content` à checagem de tipo.

Isso faz o validador aceitar PDFs reais servidos como `application/octet-stream` (ou com Content-Type ausente/incorreto), sem afrouxar a segurança: conteúdo não-PDF com tipo genérico continua sendo rejeitado.

---

## 5. FASE 5 — Verificação

### Testes atualizados/adicionados
- `backend/tests/test_file_validator.py`:
  - `test_accepts_pdf_with_octet_stream_content_type` — PDF com `application/octet-stream` aceito.
  - `test_accepts_pdf_with_unknown_content_type` — PDF com tipo genérico aceito.
  - `test_rejects_html_even_with_pdf_magic_absent` — HTML com tipo genérico rejeitado.
  - `test_rejects_missing_content_type_for_non_pdf` + `test_accepts_pdf_with_missing_content_type` (substituem o antigo `test_rejects_missing_content_type`).
- `backend/tests/test_file_storage.py`:
  - `test_save_accepts_pdf_without_content_type_metadata` + `test_save_rejects_non_pdf_without_content_type_metadata` (substituem o antigo `test_save_requires_content_type_in_metadata`).

### Cadeia completa verificada
`verify_octet_chain.py` baixou o PDF octet-stream real, salvou via `FileStorage` (com sniffing) e extraiu via `PDFExtractor`: **43 páginas, ~65k caracteres**. A cadeia download → storage → extração funciona de ponta a ponta.

### Suítes de teste
- **Backend:** 493 passed, 0 failed.
- **Frontend:** 34 passed.

---

## 6. Problemas remanescentes

- **ALTO — 403 (paywall) e HTML anti-bot:** não corrigíveis programaticamente. Documentos dessas origens continuarão sem gerar chunks. Mitigação futura possível: priorizar fontes OA confiáveis na seleção de documentos (fora do escopo deste ticket; tratada parcialmente no RDA-066 com fontes de PDF aberto e Unpaywall).
- **MÉDIO — Persistência de claims/evidence:** continuam apenas em memória (fora do escopo).

---

## 7. Artefatos

- `backend/scripts/evaluation/run_downloadability_audit.py` — harness de auditoria de downloadability.
- `backend/scripts/evaluation/classify_failures.py` — classificação das falhas por tipo real de conteúdo.
- `backend/data/evaluation/downloadability_audit_20260827T183527Z.json` — resultado bruto da auditoria.

**Mudança de código:** apenas `backend/app/services/storage/validator.py` (magic-byte sniffing) e os testes correspondentes.
