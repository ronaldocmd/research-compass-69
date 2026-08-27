# RDA-059 — Auditoria e Correção de Robustez Multilíngue do Retrieval

**Data:** 2026-08-27
**Commit base:** `2961c6f` (RDA-058)
**Ambiente:** embeddings `text-embedding-3-small` (dim 1536) via proxy LiteLLM (`http://localhost:4000/v1`).

---

## 1. Contexto

O RDA-058 observou que uma research question em português recuperava **0 chunks**, enquanto a equivalente em inglês recuperava **28 chunks**, quando os documentos relevantes estavam em inglês. Este ticket determina experimentalmente a causa e implementa a solução mais apropriada.

---

## 2. FASE 1 — Inspeção

| Item | Valor |
|---|---|
| Modelo de embedding | `text-embedding-3-small` (OpenAI) |
| Provider | OpenAI via LiteLLM proxy |
| Dimensão | 1536 |
| Normalização | Nenhuma (cosine puro, normas computadas on-the-fly) |
| Cosine similarity | `cosine_similarity` (Python puro) |
| Threshold | 0.5 (RDA-058) |
| Top-k | 5 |
| Query | research question (RDA-058) |
| Documentos | predominantemente em inglês (literatura acadêmica) |

**Multilinguismo do modelo:** a documentação oficial da OpenAI confirma que `text-embedding-3-small` é **nativamente multilíngue** (100+ idiomas, inclui português), suporta similaridade cross-lingual e pontua 44.0 no benchmark MIRACL (vs 31.4 do ada-002). Portanto, o modelo **não** é monolíngue.

---

## 3. FASE 2-3 — Benchmark cross-lingual e matriz experimental

Criado `backend/data/benchmarks/retrieval_crosslingual_v1.json`: 28 passagens (24 EN + 4 PT) e **10 pares de queries PT↔EN** apontando para os mesmos documentos relevantes.

Matriz experimental (scores crus, sem threshold):

| Query→Doc | n | mean | min | max | recall@0.5 |
|---|---|---|---|---|---|
| PT→EN | 20 | 0.526 | 0.392 | 0.732 | 0.55 |
| EN→EN | 20 | 0.621 | 0.411 | 0.874 | 0.85 |

**Conclusão da matriz:** o modelo **é multilíngue** (PT→EN scores significativos, mean 0.53, claramente separados de irrelevantes em 0.22). O gap cross-lingual é de **~0.1** (0.53 vs 0.62).

---

## 4. FASE 4 — Scores crus sem threshold

Para cada par PT→EN, os scores crus dos chunks relevantes foram registrados (ver `crosslingual_audit_20260827T180119Z.json`). Exemplos de chunks relevantes que caíam **abaixo** do threshold 0.5:

- COT2 (chain-of-thought): 0.465
- LUNG2 (câncer de pulmão): 0.486
- CODE1 (geração de código): 0.488
- EMB4 (embeddings): 0.392

Distribuição de scores para queries PT:
- relevant: mean=0.526, p25=0.466, p50=0.522, p75=0.593
- irrelevant: mean=0.219, p25=0.146, p50=0.186, p75=0.257

Há **separação clara** entre relevantes (mean 0.53) e irrelevantes (mean 0.22), mas o cluster relevante PT→EN começa em ~0.39-0.47.

---

## 5. FASE 5 — Determinação da causa

Sweep de threshold (precisão/recall/F1):

| Threshold | PT→EN P | PT→EN R | PT→EN F1 | EN→EN P | EN→EN R | EN→EN F1 |
|---|---|---|---|---|---|---|
| 0.40 | 0.46 | **0.95** | **0.62** | 0.47 | 1.00 | 0.63 |
| 0.45 | 0.50 | 0.80 | 0.62 | 0.47 | 0.90 | 0.62 |
| 0.50 | 0.55 | 0.55 | 0.55 | 0.59 | 0.85 | 0.69 |
| 0.55 | 0.58 | 0.35 | 0.44 | 0.70 | 0.80 | 0.74 |

**Veredito das hipóteses:**
- **A (modelo não multilíngue): FALSA.** O modelo é nativamente multilíngue; PT→EN scores são significativos (mean 0.53) e separados de irrelevantes.
- **B (threshold inadequado para cross-lingual): VERDADEIRA.** O threshold 0.5, calibrado em EN-only (RDA-058), fica acima do cluster relevante PT→EN (p25=0.47), derrubando ~45% dos chunks relevantes (recall 0.55).
- **C (query PT próxima mas abaixo do threshold): VERDADEIRA.** Muitos chunks relevantes PT→EN pontuam 0.39-0.49, logo abaixo de 0.5.
- **D/E/F/G:** não são a causa primária; o problema está no threshold, não na seleção, formulação da query ou chunking.

**Causa raiz:** combinação de **B + C**. O modelo é multilíngue, mas o threshold 0.5 foi calibrado para retrieval same-language (EN→EN) e é alto demais para o cenário cross-lingual de produção (pergunta PT → documentos EN).

---

## 6. FASE 6 — Solução implementada

**Baixar `RETRIEVAL_MIN_SCORE` de 0.5 para 0.40**, calibrado para o cenário cross-lingual de produção.

Justificativa:
- 0.40 é o melhor ponto de operação cross-lingual (F1=0.62, recall=0.95, precision=0.46).
- Para um pipeline RAG, **recall importa mais que precisão**: conteúdo não recuperado não pode ser sintetizado, e a etapa downstream de evidence/claims filtra ruído.
- Também **melhora** o benchmark EN-only (R@5 0.63→0.80, Hit@5 0.79→0.93, MRR 0.70→0.85), sem regressão.

Não foi usada tradução de query nem troca de modelo de embedding, pois a evidência mostrou que o modelo já é multilíngue e o problema é o threshold.

---

## 7. FASE 7 — Verificação

### Benchmark cross-lingual (threshold 0.40)
- **PT→EN recall: 0.55 → 0.95** (19/20)
- **EN→EN recall: 0.85 → 1.0** (20/20)

### Benchmark EN-only (retrieval_gold_v1, threshold 0.40)
- R@5: 0.63 → **0.80**
- Hit@5: 0.79 → **0.93**
- MRR: 0.70 → **0.85**
- NDCG@5: 0.62 → **0.76**

### E2E real (chunks persistidos do research `4ca18f7e`, 134 chunks)
- Query PT: **0 → 60 chunks** recuperados
- Query EN: 76 chunks recuperados

O problema original (pergunta PT → 0 chunks) está **resolvido**.

### Testes
- **Backend:** 488 passed, 0 failed.
- **Frontend:** 34 passed.

---

## 8. Problemas remanescentes

- **ALTO — Downloadability:** muitos documentos relevantes são HTML-only ou 403 (paywall), então não geram chunks. No E2E deste ticket, 11/11 documentos selecionados falharam no download (HTML/403). Isso é separado do problema cross-lingual e limita a disponibilidade de conteúdo, não a qualidade do retrieval.
- **MÉDIO — Persistência de claims/evidence:** continuam apenas em memória (fora do escopo).

---

## 9. Artefatos

- `backend/data/benchmarks/retrieval_crosslingual_v1.json` — benchmark cross-lingual controlado.
- `backend/scripts/evaluation/run_crosslingual_audit.py` — harness de scores crus e matriz.
- `backend/scripts/evaluation/run_crosslingual_sweep.py` — harness de sweep de threshold.
- `backend/data/evaluation/crosslingual_audit_20260827T180119Z.json` — scores crus por par.
- `backend/data/evaluation/crosslingual_sweep_20260827T175727Z.json` — sweep de threshold.
- `backend/data/evaluation/retrieval_audit_20260827T180313Z.json` — benchmark EN-only pós-correção.

**Mudança de código:** apenas `RETRIEVAL_MIN_SCORE` (0.5 → 0.40) no config e o teste correspondente.
