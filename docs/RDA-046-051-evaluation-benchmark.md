# RDA-046 a RDA-051 — Avaliação e Benchmark (Sprint 7)

Dataset de benchmark versionado e quatro dimensões de avaliação do agente:
evidência (objetiva), humana, custo e performance.

> **Nota de organização:** `benchmark` e `evidence` vivem em
> `backend/app/evaluation/`; `cost` (usage) e `performance` vivem em
> `backend/app/services/{usage,performance}/`. Não existem arquivos
> `app/evaluation/cost.py` nem `app/evaluation/performance.py` — a
> localização é assimétrica entre os quatro tipos de avaliação.

## Dataset de benchmark versionado (RDA-046)

`backend/app/evaluation/benchmark.py`:

- `BenchmarkQuestion{id, question, objective, language="pt", depth: superficial|medium|deep, expected_sources, evaluation_criteria (mín. 1)}`.
- `BenchmarkDataset{version, created_at, questions}` — valida IDs de questão únicos.
- `load_benchmark(version="v1.0")` carrega de `backend/data/benchmarks/{version}.json`.

Dados: `backend/data/benchmarks/v1.0.json` + `backend/data/benchmarks/README.md`
(formato do arquivo e regra de versionamento semântico: nunca alterar uma
versão já publicada/usada — criar `v1.1.json` para adições compatíveis).

## Evidence evaluation (RDA-048)

`backend/app/evaluation/evidence.py` — avaliação **objetiva, sem LLM**:

- `ClaimEvidenceStatus{claim_id, claim_text, has_evidence, evidence_count, has_grounding, provenance_complete}`.
- `EvidenceEvaluationResult{research_id, total_claims, claims_with_evidence, claims_with_evidence_pct, grounding_rate, provenance_completeness, unsupported_claims}`.
- `EvidenceEvaluator(claim_loader, evidence_loader)` depende de loaders
  injetados (claims/evidence são DTOs do pipeline, não persistidos em tabela
  própria). `write_evaluation_report()` grava o resultado em JSON.

CLI: `backend/scripts/run_benchmark.py --evidence --benchmark-version v1.0
--research-id <uuid> [--research-id ...]`. Sem loaders configurados
programaticamente, o `main()` apenas valida o dataset.

## Human evaluation (RDA-049)

| Camada     | Arquivo                                                        |
| ---------- | ------------------------------------------------------------------ |
| Model      | `backend/app/models/human_evaluation.py` (tabela `human_evaluations`, append-only) |
| Repository | `backend/app/repositories/evaluation_repository.py::EvaluationRepository` |
| Schemas    | `backend/app/schemas/evaluation.py`                                 |

Campos: `id`, `claim_id` (UUID sem FK — claims são DTOs, não persistidos),
`research_id`, `evaluator_id`, `rating` (`correct|incorrect|inconclusive`),
`comment`, `evaluated_at`. Migration: `a01d7803a94d_add_human_evaluations_table`.

`EvaluationRepository`: `create_evaluation`, `get_by_claim`, `get_by_research`,
`get_statistics`. Schemas: `HumanEvaluationCreate`, `HumanEvaluationResponse`,
`EvaluationStats{total, correct, incorrect, inconclusive}` (percentuais 0..1).

### Endpoints (`api/v1/endpoints/evaluations.py`)

| Método | Rota                                                | Observação                                    |
| ------ | ----------------------------------------------------- | ------------------------------------------------ |
| POST   | `/api/v1/evaluations`                                 | 201                                                |
| GET    | `/api/v1/evaluations?claim_id=`                       | Retorna `[]` se `claim_id` for omitido (não lista todas) |
| GET    | `/api/v1/researches/{research_id}/evaluations`        |                                                    |
| GET    | `/api/v1/researches/{research_id}/evaluation-stats`   |                                                    |

## Cost evaluation (RDA-050)

`backend/app/services/usage/tracker.py`:

- Funções puras: `calculate_llm_cost(model, input_tokens, output_tokens)`
  (usa `settings.LLM_PRICING`, retorna `0.0` para modelo desconhecido),
  `calculate_search_cost(provider)` (usa `settings.SEARCH_PRICING`).
- `UsageTracker(db)`: `record_llm_call(research_id, model, input_tokens, output_tokens)`
  e métodos análogos para custo de busca/processamento;
  `get_total_cost(research_id)`, `get_report(research_id)`.

Model: `backend/app/models/usage_event.py` (tabela `usage_events`).
Migration: `b2c9e5f1a3d7_add_usage_events_table`.

> `BudgetGuard` (ver `RDA-031-037-orchestration.md`) enforça limites **em
> memória durante a execução**; `UsageTracker` é a camada de **persistência
> para auditoria/relatórios pós-execução** — são complementares, não
> substitutos um do outro.

## Performance evaluation com tracking por estágio (RDA-051)

`backend/app/services/performance/tracker.py`:

- Funções puras: `calculate_time_to_first_result` (do início até a conclusão
  do estágio "search"), `calculate_time_to_completion`,
  `calculate_throughput` (docs/min), `calculate_error_rate` (fração de
  estágios com `status="failed"`).
- `PerformanceTracker(db)`: `start_stage(research_id, stage)` /
  `end_stage(...)` gravam uma linha por estágio (append-only) em
  `PerformanceMetric`; `get_report(research_id, documents_found, documents_processed)`
  monta `PerformanceReport`.

Model: `backend/app/models/performance_metric.py` (tabela
`performance_metrics`; `stage`: planning|search|processing|evidence|synthesis;
`status`: success|failed). Migration: `d4e9b7c3f5a1_add_performance_metrics_table`.

Schemas (`backend/app/schemas/performance.py`):
`StageMetric{stage, duration_seconds, status}`,
`PerformanceReport{research_id, time_to_first_result, time_to_completion,
documents_found, documents_processed, throughput_docs_per_minute, error_rate, stages}`.

**Integração:** `api/v1/endpoints/run.py` injeta `PerformanceTracker(db)` no
`ResearchOrchestrator` a cada `POST /researches/{id}/run` quando a pesquisa
existe no banco.

CLI: `backend/scripts/run_performance_benchmark.py` — roda o workflow
completo para cada questão do benchmark (`uuid5(NAMESPACE_URL,
f"benchmark:{question.id}")` como `research_id` determinístico), grava um
`PerformanceTracker` por execução e escreve relatório JSON em
`data/performance/{question.id}.json`. Exige `orchestrator` e `db`
configurados — chamado sem eles, apenas valida o dataset.

## Testes

`backend/tests/`: `test_benchmark_dataset.py`, `test_evidence_evaluation.py`,
`test_evaluation_repository.py`, e a suíte de `services/` para usage/performance.
