# RDA-058 — Correção e Calibração da Cadeia de Relevância Upstream

**Data:** 2026-08-27
**Commit base:** `e2973fc` (RDA-057)
**Ambiente:** embeddings `text-embedding-3-small` (dim 1536) e LLM via proxy LiteLLM (`http://localhost:4000/v1`).

---

## 1. Contexto

O RDA-057 (auditoria) identificou que a causa raiz do E2E sem dados não era o retrieval nem a evidence, mas a **cadeia de seleção/download** (índice poluído com documentos fora do tópico) somada ao **threshold de retrieval mal calibrado** (0.7). Este ticket corrige e calibra essa cadeia.

---

## 2. Correções realizadas

### 2.1 Threshold de retrieval calibrado (FASE 6-8)
`RETRIEVAL_MIN_SCORE` mudou de **0.7 → 0.5**, calibrado empiricamente no benchmark gold do RDA-057. O valor 0.7 ficava acima do cluster de relevantes (p75≈0.65) e colapsava o recall.

| Métrica | Antes (0.7) | Depois (0.5) |
|---|---|---|
| R@5 | 0.14 | **0.63** |
| Hit@5 | 0.14 | **0.79** |
| MRR | 0.14 | **0.70** |
| NDCG@5 | 0.14 | **0.62** |
| P@1 | 0.14 | **0.64** |

### 2.2 Query de retrieval corrigida (FASE 5)
O nó de evidence usava `task.title` (instrução genérica de extração) como query de retrieval. Agora usa a **research question** (`RETRIEVAL_QUERY_STRATEGY="question"`), capturada no state durante o planejamento.

Comparação medida no benchmark gold (threshold 0.5):

| Variante | R@5 | Hit@5 | MRR | NDCG@5 |
|---|---|---|---|---|
| A) task.title genérico (antigo) | 0.00 | 0.00 | 0.00 | 0.00 |
| B) research.question (novo) | **0.63** | **0.79** | **0.70** | **0.62** |
| C) question + description | 0.57 | 0.71 | 0.63 | 0.55 |

### 2.3 Document selection por relevância (FASE 2-4)
O `selection_node` agora filtra resultados de busca por **similaridade com a research question** (`SELECTION_MIN_SCORE=0.3`), separando relevância de downloadability. Um resultado é descartado por irrelevância na seleção, nunca por falta de PDF (isso é tratado no processamento).

### 2.4 Downloadability observável (FASE 4)
O `WorkflowServices.process` agora retorna um `ProcessResult` com `reason` quando o documento não pode ser processado (sem URL, download falhou, storage rejeitou HTML, extração falhou). O `processing_node` registra o motivo em `processing_status` (ex: `failed:storage_rejected: ...`), distinguindo indisponibilidade técnica de irrelevância.

### 2.5 Observabilidade mínima (FASE 13)
O state ganhou `selection_stats` com contadores end-to-end:
- `search_results`, `selected`, `discarded_irrelevant`, `discarded_duplicate`
- `processed`, `failed`, `chunk_count`

### 2.6 Quality gate do retrieval (FASE 14)
O `synthesis_node` agora **não gera summary a partir de contexto vazio**. Com 0 claims, registra um aviso não-fatal ("Synthesis skipped: no claims were produced") e completa sem fabricar um summary tipo "No claims were provided...".

### 2.7 Fallback OpenAlex (FASE 3)
Já corrigido no RDA-056 (prefere `best_oa_location.pdf_url` → `primary_location.pdf_url` → `open_access.oa_url`). Testes existentes cobrem o fallback.

---

## 3. E2E real (FASE 12)

### Research `0ccc96f8` (pergunta em português)
- **STAGE: COMPLETED** (antes FAILED)
- 40 resultados → **6 selecionados** (34 descartados por irrelevância) → 1 processado + 5 indisponíveis (HTML)
- 39 chunks persistidos
- Documento processado: **PRISMA-ScR** (relevante para revisão sistemática)
- Quality gate ativo: "Synthesis skipped: no claims were produced"

### Research `4ca18f7e` (pergunta em inglês)
- 40 resultados → 4 documentos processados, **todos relevantes** (PRISMA-ScR, PRISMA Statement, Scoping studies)
- **134 chunks persistidos**
- Run interrompido por `ConnectionResetError` (falha de infraestrutura) durante a fase de evidence/claims

### Observabilidade demonstrada
```
selection_stats: {"search_results":40, "selected":6, "discarded_irrelevant":34,
                  "discarded_duplicate":0, "processed":1, "failed":5, "chunk_count":39}
```

---

## 4. Testes

- **Backend:** 488 passed, 0 failed (inclui novos testes de seleção por relevância, query de retrieval, indisponibilidade, quality gate, e reprodução do cenário grupos A-E).
- **Frontend:** 34 passed.
- **Benchmark gold:** reexecutado, sem regressão (R@5=0.63, Hit@5=0.79, MRR=0.70).

Novos testes:
- `test_selection_node_filters_by_relevance`
- `test_selection_node_without_question_selects_all`
- `test_processing_node_records_unavailability_reason`
- `test_retrieval_query_uses_research_question`
- `test_retrieval_query_falls_back_to_task_title`
- `test_selection_processing_separates_relevance_from_downloadability` (grupos A-E)
- `test_synthesis_node_skips_when_no_claims`

---

## 5. Problemas remanescentes

- **ALTO — Cross-lingual:** a research question em português tem similaridade baixa com chunks em inglês (query PT → 0 chunks; query EN → 28 chunks). O filtro de seleção tolera isso (títulos são mais genéricos), mas o retrieval de chunks sofre. Solução futura: traduzir a query ou usar embeddings multilingues.
- **ALTO — Falhas transitórias do provider:** o planner (modelo free) gerou prioridade de tarefa inválida (6) em alguns runs; o run E2E foi interrompido por `ConnectionResetError`. Não são defeitos do RDA-058.
- **MÉDIO — Persistência de claims/evidence:** claims/evidence continuam apenas em memória (não persistidos). Fora do escopo deste ticket.

---

## 6. Artefatos

- `backend/scripts/evaluation/compare_query_strategies.py` — harness de comparação de variantes de query.
- `backend/data/evaluation/query_strategy_20260827T170938Z.json` — resultado da comparação.
- `backend/data/evaluation/retrieval_audit_20260827T174502Z.json` — benchmark pós-calibração.

**Nenhuma correção de código foi aplicada fora do escopo do RDA-058.**
