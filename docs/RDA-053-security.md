# RDA-053 — Hardening de Segurança

Auditoria de segurança do Research Discovery Agent e correção das
vulnerabilidades concretas encontradas. O escopo cobre backend (FastAPI),
frontend (Next.js) e configuração de deploy (Docker).

## Resumo

| Severidade | Qtd | Descrição |
| ---------- | --- | --------- |
| Crítico    | 0   | — |
| Alto       | 1   | SSRF no `DocumentDownloader` (corrigido) |
| Médio      | 0   | — |
| Baixo      | 2   | `backend/.env.example` ausente (corrigido); CORS permissivo (documentado) |

## Metodologia

1. **Setup**: estado do git, histórico, estrutura, configuração.
2. **Baseline**: suíte de testes antes das mudanças — **449 passed, 16 skipped**.
3. **Auditoria** por categoria (segredos, CORS, auth, SSRF, uploads, input,
   SQL, logs, erros, endpoints, exposição de dados, frontend, dependências).
4. **Classificação** e plano de correção.
5. **Correção** com a menor mudança possível + testes de regressão.
6. **Verificação**: suíte completa após as mudanças — **459 passed, 16 skipped**.

## Auditoria por categoria

### Segredos (Fase 3) — OK
- Nenhum segredo hardcoded no código (`sk-*`, `Bearer`, senhas, API keys).
- `OPENAI_API_KEY` é um campo de configuração com default `None`; nunca é
  logado nem exposto.
- `.env` está no `.gitignore`; apenas `.env.example` é versionado.
- Nenhum `.env` ou arquivo de segredo no histórico do git.

### CORS (Fase 4) — OK (documentado)
- `allow_origins` vem de `BACKEND_CORS_ORIGINS` (default `http://localhost:3000`),
  não `*`. `allow_credentials=True` com origem específica é aceitável.
- `allow_methods=["*"]` e `allow_headers=["*"]` são permissivos, mas não
  representam risco concreto com origem restrita. **Baixo** — sem mudança.

### Autenticação (Fase 5) — Documentado (não corrigido)
- Nenhum endpoint exige autenticação. Para um MVP sem dados sensíveis e sem
  endpoints administrativos, isso **não** é classificado como crítico.
- Recomendação futura: adicionar autenticação (ex.: API key ou OAuth) antes
  de expor o serviço publicamente. Fora do escopo desta tarefa.

### SSRF (Fase 6) — ALTO (corrigido)
O `DocumentDownloader` baixa URLs que vêm de resultados de busca externos
(OpenAlex/Crossref). Um resultado malicioso ou um provedor comprometido
poderia apontar para `http://169.254.169.254/` (metadata de nuvem),
`http://localhost:...` ou serviços de rede interna, e o downloader faria o
fetch. Não havia validação de esquema, bloqueio de IPs privados, limite de
redirecionamentos nem proteção contra DNS rebinding.

**Correção** (`backend/app/services/downloader/ssrf.py` + `downloader.py`):
- Novo `SSRFGuard` que valida o esquema (apenas `http`/`https`), resolve o
  hostname e bloqueia qualquer endereço em redes privadas, loopback,
  link-local (incl. metadata `169.254.169.254`), CGNAT, documentação,
  multicast e reservadas (IPv4 e IPv6, incluindo IPv4-mapped).
- O guard é injetável (resolver customizável) para testes sem DNS real.
- `download()` valida a URL antes de qualquer request.
- Redirecionamentos limitados a `MAX_REDIRECTS = 5` e cada hop é revalidado
  por um transport customizado.

**Limitação conhecida**: a validação resolve o host e bloqueia IPs privados,
mas não fixa o IP da conexão (TOCTOU de DNS rebinding). Uma mitigação
completa exigiria pinar o IP no transport, o que é mais invasivo; documentado
como melhoria futura.

### Uploads / Arquivos (Fase 7) — OK
- Nenhum endpoint de upload de usuário.
- `FileStorage` usa `document_id` (UUID) no caminho — sem path traversal.
- `FileValidator` restringe a `application/pdf` e limita o tamanho.

### Validação de input (Fase 8) — OK
- Schemas Pydantic com `extra="forbid"`, limites de tamanho e
  `str_strip_whitespace`. URLs normalizadas para `http`/`https`.

### SQL Injection (Fase 9) — OK
- Todo acesso a banco via SQLAlchemy ORM com queries parametrizadas.
- Nenhum SQL concatenado com input do usuário.

### Logs (Fase 10) — OK
- Nenhum segredo é logado. Apenas `main.py` e `health_repository.py` logam
  (mensagens não sensíveis).

### Erros (Fase 11) — OK
- Sem `debug=True`, sem exposição de traceback, sem exception handlers que
  vazem detalhes internos.

### Endpoints (Fase 12) — OK
- Nenhum endpoint perigoso além da ausência geral de auth (documentada).

### Exposição de dados (Fase 13) — OK
- Schemas de resposta não expõem segredos nem campos internos.

### Frontend (Fase 14) — OK
- Nenhum segredo no frontend. Apenas `NEXT_PUBLIC_API_URL` (URL pública, não
  é segredo).

### Dependências (Fase 15) — Não auditado
- `pip-audit` não está instalado e não foi instalado (evitando novas
  dependências). Recomenda-se rodar `pip-audit` em CI.

## Correções aplicadas

1. **SSRF (Alto)** — `backend/app/services/downloader/ssrf.py` (novo),
   `backend/app/services/downloader/downloader.py` (guard + redirects),
   `backend/tests/test_document_downloader.py` (10 testes de regressão).
2. **`backend/.env.example` (Baixo)** — criado com todas as variáveis do
   backend, seguindo o estilo do `.env.example` raiz. O `.env` real continua
   ignorado pelo git.

## Verificação

- Baseline: **449 passed, 16 skipped**.
- Após correções: **459 passed, 16 skipped** (10 novos testes de SSRF).
- Testes do downloader: **23 passed** (13 originais + 10 novos).
- Sanity check com DNS real: host público aceito; `localhost`, `127.0.0.1` e
  `169.254.169.254` bloqueados.
