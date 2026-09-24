# RDA-031 a RDA-037 — Orquestração (Sprint 4/5)

Planejamento estruturado de pesquisa, execução do workflow via LangGraph,
checkpoint/resume, retry com classificação de erro e guarda de orçamento.

## Planner (RDA-030/031)

`backend/app/services/planning/planner.py::ResearchPlanner.plan()` — usa um
`LLMProvider` abstrato (implementação `OpenAILLMProvider`), chamada síncrona
via `asyncio.to_thread`. Gera `ResearchPlan` a partir de `ResearchPlanInput`,
validando e convertendo `PlanTaskDraft` → `PlanTask`.

| Camada     | Arquivo                                                   |
| ---------- | ----------------------------------------------------------- |
| Service    | `backend/app/services/planning/planner.py`, `research_plan_service.py` |
| Repository | `backend/app/repositories/research_plan_repository.py`, `plan_task_repository.py` |
| Model      | `backend/app/models/plan.py` (`ResearchPlanRecord`, `PlanTaskRecord`) |

Migration: `alembic/versions/0005_research_plans.py`.

### Endpoints (`api/v1/endpoints/plan.py`)

| Método | Rota                                | Sucesso | Erros                                                    |
| ------ | ------------------------------------ | ------- | ---------------------------------------------------------- |
| POST   | `/api/v1/researches/{id}/plan`       | 201     | 404 (`ResearchNotFoundError`), 422 (`InvalidPlanError`), 502 (`PlanningError`) |
| GET    | `/api/v1/researches/{id}/plan`       | 200     | 404 (`ResearchNotFoundError` / `ResearchPlanNotFoundError`) |
| GET    | `/api/v1/researches/{id}/plan/tasks` | 200     | 404                                                          |

## Estado do workflow (RDA-032)

`backend/app/services/workflow/state.py`:

- `WorkflowStage`: `IDLE, PLANNING, SEARCH(=SEARCHING), SELECTING, PROCESSING, EXTRACTING, VALIDATING, SYNTHESIZING, COMPLETED, PAUSED, FAILED, BUDGET_EXCEEDED`.
- `ResearchWorkflowState` (Pydantic, serializável para JSON/checkpoint):
  `research_id`, `execution_id`, `current_stage`, `plan_id`, `tasks`,
  `search_queries`, `search_results`, `selected_documents`/`selected_ids`,
  `processed_document_ids`, `failed_document_ids`, `processing_status`,
  `chunk_ids`, `claims`, `evidence_items`, `errors: list[WorkflowError]`,
  `retry_count`, `budget: BudgetState`, timestamps (`started_at`, `updated_at`,
  `completed_at`, `checkpointed_at`).
- `BudgetState`: contadores (`llm_calls`, `total_tokens`, `search_calls`,
  `processing_operations`, `estimated_cost_usd`) + limites (`max_llm_calls=50`,
  `max_search_calls=20`, `max_processing_operations=100`, `max_cost_usd=5.0`) + `is_exceeded`.
- `WorkflowError{error_id, stage, message, severity: ErrorSeverity, timestamp, retryable, context}`.
- `state_manager.py::WorkflowStateManager` — helpers puros/imutáveis
  (`create_initial_state`, `transition`, retornando cópias via `model_copy`).

## Grafo LangGraph (RDA-033/034)

`backend/app/services/orchestration/graph.py::build_graph(nodes)`

- Nodes (`services/orchestration/nodes.py::ResearchNodes`): `planner`, `search`,
  `selection`, `processing`, `evidence`, `synthesis`, `complete`,
  `budget_exceeded`, `failed`.
- Fluxo: `START → planner → search → selection → processing → evidence →
  synthesis → {complete|budget_exceeded|failed} → END`.
- Roteamento condicional: `route_after_node` interrompe assim que
  `state.current_stage == BUDGET_EXCEEDED`; `route_after_synthesis` decide o
  nó terminal (`budget_exceeded` se orçamento estourado, `failed` se houver
  `WorkflowError` com `severity == PERMANENT`, senão `complete`).
- `ResearchNodes` aceita `performance_tracker` e `checkpoint_manager`
  opcionais; quando `checkpoint_manager` está presente, cada node persiste o
  estado ao final.

> **Dois orquestradores coexistem no código:**
> - `orchestration/orchestrator.py::ResearchOrchestrator` — usa LangGraph,
>   **é o mecanismo ativo** (referenciado por `api/v1/endpoints/run.py` e
>   pelo benchmark de performance). Mantém estado em memória
>   (`dict[uuid.UUID, ResearchWorkflowState]`) e **não** injeta
>   `checkpoint_manager` por padrão — checkpointing real não está ligado no
>   fluxo de produção atual.
> - `workflow/orchestrator.py::WorkflowOrchestrator` (RDA-035) — orquestrador
>   mais simples, sem LangGraph, com resume via `CheckpointManager.load_latest`.
>   Não é referenciado por nenhum endpoint HTTP encontrado — parece um
>   protótipo anterior ao LangGraph ou uma via alternativa ainda não
>   conectada. **Recomenda-se confirmar se é código morto/experimental**
>   antes de tratá-lo como o mecanismo de resume em produção.

## Checkpoint / resume (RDA-035)

| Camada     | Arquivo                                                       |
| ---------- | ---------------------------------------------------------------- |
| Model      | `backend/app/models/workflow_checkpoint.py` (tabela `workflow_checkpoints`) |
| Service    | `backend/app/services/workflow/checkpoint_manager.py::CheckpointManager` |

Migration: `alembic/versions/20260825_0005_workflow_checkpoints.py`.

`CheckpointManager.save(state)` marca checkpoints anteriores da mesma
`execution_id` como `is_latest=False` antes de inserir o novo;
`load_latest(execution_id)` e `load_by_stage(execution_id, stage)` recuperam
estado salvo. `WorkflowOrchestrator.run()` restaura o checkpoint mais recente
antes de rodar — se `current_stage == COMPLETED`, retorna direto; senão
continua a partir do estágio salvo, sem repetir estágios já concluídos.

## Retry e classificação de erro (RDA-036)

`backend/app/services/workflow/retry_handler.py`:

- `RetryPolicy`: `max_attempts=3`, `base_delay_seconds=1.0`,
  `max_delay_seconds=30.0`, `exponential_base=2.0`,
  `retryable_severities=[TRANSIENT, PROVIDER]`.
- `RetryHandler.classify_error()` mapeia exceções para `ErrorSeverity`:
  timeouts (`asyncio.TimeoutError`, `httpx.TimeoutException`,
  `APITimeoutError`) → TRANSIENT; `httpx.HTTPStatusError`/`APIStatusError`
  com 429 → TRANSIENT (outros códigos → PROVIDER); `RateLimitError` /
  `APIConnectionError` → TRANSIENT; `APIError` genérico → PROVIDER;
  `ValidationError` (pydantic) → VALIDATION.
- Backoff exponencial baseado em `base_delay_seconds` × `exponential_base^tentativa`, limitado por `max_delay_seconds`.

## Budget guard (RDA-037)

`backend/app/services/workflow/budget_guard.py`:

- `BudgetConfig`: limites (`max_llm_calls`, `max_search_calls`,
  `max_processing_operations`, `max_cost_usd`) + custos unitários
  (`cost_per_llm_call_usd=0.01`, `cost_per_search_call_usd=0.005`,
  `cost_per_1k_tokens_usd=0.002`).
- `BudgetGuard.check_before_llm_call/search/processing(state)` levanta
  `BudgetExceededError(operation, detail)` se a operação ultrapassaria o
  limite; `record_llm_call(state, tokens_used)` retorna novo estado
  (imutável) com contadores e custo atualizados.

## Endpoints de execução (`api/v1/endpoints/run.py`)

| Método | Rota                             | Descrição                                                                 |
| ------ | ---------------------------------- | ---------------------------------------------------------------------------- |
| POST   | `/api/v1/researches/{id}/run`      | Dispara `ResearchOrchestrator.run(research_id)`; grava `started_at`/`completed_at` em `Research`; injeta `PerformanceTracker(db)` (RDA-051) |
| GET    | `/api/v1/researches/{id}/status`   | Retorna `WorkflowStatusResponse` (extensão de `ResearchWorkflowState` com campo `stage`); 404 via `OrchestrationError` |

## Testes

`backend/tests/`: `test_budget_guard.py`, `test_checkpoint_manager.py`, e a suíte
de `services/` cobrindo planner, nodes e retry (ver `backend/tests/services/`).
