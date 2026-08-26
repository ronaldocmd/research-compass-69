"""Workflow nodes (RDA-034).

Each node receives and returns a ResearchWorkflowState and has a single
responsibility. Nodes delegate to the existing services (planner, search,
retrieval, claims, evidence, synthesis) — never reimplementing logic. Errors
are handled locally (recorded into state.errors) so a failure in one step
does not crash the workflow. Every mutation returns a new state.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from app.services.planning.schemas import ResearchPlanInput, TaskType
from app.services.workflow.state import (
    ErrorSeverity,
    ResearchWorkflowState,
    WorkflowError,
    WorkflowStage,
)
from app.services.workflow.retry_handler import RetryHandler, RetryPolicy
from app.services.workflow.budget_guard import (
    BudgetConfig,
    BudgetExceededError,
    BudgetGuard,
)
from app.services.workflow.state_manager import WorkflowStateManager

_SELECTION_NAMESPACE = uuid.UUID("8f1c2a3e-4b5d-4e6f-9a7b-0c1d2e3f4a5b")


class SynthesisResponse(BaseModel):
    """Structured-output contract for the synthesis node."""

    model_config = ConfigDict(extra="forbid")

    summary: str


class ResearchNodes:
    """Node implementations for the research workflow graph."""

    def __init__(
        self,
        *,
        planner=None,
        search=None,
        retriever=None,
        claim_extractor=None,
        evidence_extractor=None,
        processor=None,
        llm=None,
        research_loader=None,
        summary_saver=None,
        max_documents: int = 20,
        retry_handler: RetryHandler | None = None,
        retry_policy: RetryPolicy | None = None,
        budget_guard: BudgetGuard | None = None,
        budget_config: BudgetConfig | None = None,
        checkpoint_manager=None,
    ) -> None:
        self._planner = planner
        self._search = search
        self._retriever = retriever
        self._claim_extractor = claim_extractor
        self._evidence_extractor = evidence_extractor
        self._processor = processor
        self._llm = llm
        self._research_loader = research_loader
        self._summary_saver = summary_saver
        self._max_documents = max_documents
        self._retry_handler = retry_handler or RetryHandler(retry_policy)
        self._budget_guard = budget_guard or BudgetGuard(budget_config)
        self._checkpoint_manager = checkpoint_manager

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _record_error(
        state, stage, message, *, severity=ErrorSeverity.PROCESSING, retryable=False, context=None
    ):
        error = WorkflowError(
            error_id=uuid.uuid4(),
            stage=stage,
            message=message,
            severity=severity,
            timestamp=datetime.now(UTC),
            retryable=retryable,
            context=context or {},
        )
        return WorkflowStateManager.add_error(state, error)

    async def _execute_external(
        self, state, stage, func, *args, budget_operation=None,
        terminal_on_failure=True, **kwargs
    ):
        """Run one external operation and convert its final failure to state."""
        if budget_operation is not None:
            try:
                self._check_budget(state, budget_operation)
            except BudgetExceededError as exc:
                return await self._handle_budget_exceeded(state, stage, exc)
        if state.retry_count >= 10:
            state = self._record_error(
                state, stage, "Global retry limit reached",
                severity=ErrorSeverity.PERMANENT,
                context={"retry_count": state.retry_count, "global_limit": 10},
            )
            failed_state = WorkflowStateManager.transition(state, WorkflowStage.FAILED)
            return (failed_state if terminal_on_failure else state), None, True

        remaining_attempts = min(self._retry_handler.policy.max_attempts, 10 - state.retry_count)
        policy = self._retry_handler.policy.model_copy(update={"max_attempts": remaining_attempts})
        try:
            result = await self._retry_handler.execute_with_retry(
                func, *args, policy=policy, **kwargs
            )
        except Exception as exc:
            retries = self._retry_handler.last_retry_count
            state = state.model_copy(update={"retry_count": state.retry_count + retries})
            severity = self._retry_handler.last_severity or ErrorSeverity.PERMANENT
            state = self._record_error(
                state, stage, str(exc),
                severity=severity,
                retryable=severity in policy.retryable_severities,
                context={
                    "attempts": self._retry_handler.last_attempts,
                    "retries": retries,
                    "retry_count": state.retry_count,
                },
            )
            failed_state = WorkflowStateManager.transition(state, WorkflowStage.FAILED)
            return (failed_state if terminal_on_failure else state), None, True

        retries = self._retry_handler.last_retry_count
        state = state.model_copy(update={"retry_count": state.retry_count + retries})
        if retries:
            state = self._record_error(
                state, stage, "Operation succeeded after retry",
                severity=self._retry_handler.last_severity or ErrorSeverity.TRANSIENT,
                retryable=True,
                context={
                    "attempts": self._retry_handler.last_attempts,
                    "retries": retries,
                    "retry_count": state.retry_count,
                },
            )
        if budget_operation == "llm":
            state = self._budget_guard.record_llm_call(state, self._tokens_used(result))
        elif budget_operation == "search":
            state = self._budget_guard.record_search_call(state)
        elif budget_operation == "processing":
            state = self._budget_guard.record_processing(state)
        if budget_operation is not None and self._budget_guard.is_exceeded(state):
            return await self._handle_budget_exceeded(
                state, stage,
                BudgetExceededError(budget_operation, "limit reached after operation"),
            )
        if state.retry_count >= 10:
            state = self._record_error(
                state, stage, "Global retry limit reached",
                severity=ErrorSeverity.PERMANENT,
                context={"retry_count": state.retry_count, "global_limit": 10},
            )
            failed_state = WorkflowStateManager.transition(state, WorkflowStage.FAILED)
            return (failed_state if terminal_on_failure else state), None, True
        return state, result, False

    def _check_budget(self, state, operation):
        checks = {
            "llm": self._budget_guard.check_before_llm_call,
            "search": self._budget_guard.check_before_search,
            "processing": self._budget_guard.check_before_processing,
        }
        checks[operation](state)

    async def _handle_budget_exceeded(self, state, stage, exception):
        budget = state.budget.model_copy(update={"is_exceeded": True})
        state = state.model_copy(update={"budget": budget})
        state = self._record_error(
            state, stage, str(exception), severity=ErrorSeverity.PROCESSING,
            context={"operation": exception.operation, "detail": exception.detail},
        )
        state = WorkflowStateManager.transition(state, WorkflowStage.BUDGET_EXCEEDED)
        if self._checkpoint_manager is not None:
            await self._checkpoint_manager.save(state)
        return state, None, True

    @staticmethod
    def _tokens_used(result) -> int:
        usage = getattr(result, "usage", None)
        if usage is None and isinstance(result, dict):
            usage = result.get("usage")
        if usage is None:
            return 0
        if isinstance(usage, dict):
            return int(usage.get("total_tokens", 0))
        return int(getattr(usage, "total_tokens", 0))

    # --- nodes ---------------------------------------------------------------

    async def planner_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        state = WorkflowStateManager.transition(state, WorkflowStage.PLANNING)
        if self._planner is None or self._research_loader is None:
            return state
        state, research, failed = await self._execute_external(
            state, WorkflowStage.PLANNING, self._research_loader, state.research_id
        )
        if failed:
            return state
        if research is None:
            return self._record_error(
                state, WorkflowStage.PLANNING, "Research not found",
                severity=ErrorSeverity.PERMANENT,
            )
        state, plan, failed = await self._execute_external(
            state, WorkflowStage.PLANNING, self._planner.plan,
            ResearchPlanInput(
                research_id=state.research_id,
                objective=research.objective,
                question=research.question,
            ),
            budget_operation="llm",
        )
        if failed:
            return state
        state = state.model_copy(update={"plan_id": plan.plan_id, "tasks": plan.tasks})
        return WorkflowStateManager.transition(state, WorkflowStage.SEARCHING)

    async def search_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        state = WorkflowStateManager.transition(state, WorkflowStage.SEARCHING)
        if self._search is None:
            return WorkflowStateManager.transition(state, WorkflowStage.SELECTING)
        queries = list(state.search_queries)
        if not queries:
            queries = [
                task.title for task in state.tasks if task.task_type == TaskType.SEARCH
            ]
        results = list(state.search_results)
        for query in queries:
            state, query_results, failed = await self._execute_external(
                state, WorkflowStage.SEARCHING, self._search.search, query,
                budget_operation="search",
            )
            if failed:
                return state
            results.extend(query_results)
        state = state.model_copy(update={"search_results": results})
        return WorkflowStateManager.transition(state, WorkflowStage.SELECTING)

    async def selection_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        state = WorkflowStateManager.transition(state, WorkflowStage.SELECTING)
        seen: set = set()
        selected_ids: list = []
        for result in state.search_results:
            key = result.doi or (result.title or "").strip().lower() or result.external_id
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            selected_ids.append(self._result_id(result))
            if len(selected_ids) >= self._max_documents:
                break
        state = state.model_copy(update={"selected_documents": selected_ids})
        return WorkflowStateManager.transition(state, WorkflowStage.PROCESSING)

    @staticmethod
    def _result_id(result):
        key = result.doi or result.external_id or result.title or result.source or ""
        return uuid.uuid5(_SELECTION_NAMESPACE, key)

    async def processing_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        state = WorkflowStateManager.transition(state, WorkflowStage.PROCESSING)
        if self._processor is None:
            return WorkflowStateManager.transition(state, WorkflowStage.EXTRACTING)
        processed = list(state.processed_document_ids)
        failed = list(state.failed_document_ids)
        chunk_ids = list(state.chunk_ids)
        status = dict(state.processing_status)
        for doc_id in state.selected_documents:
            if doc_id in processed or doc_id in failed:
                continue
            state, chunks, failed_operation = await self._execute_external(
                state, WorkflowStage.PROCESSING, self._processor, doc_id,
                budget_operation="processing", terminal_on_failure=False,
            )
            if failed_operation:
                if state.current_stage == WorkflowStage.BUDGET_EXCEEDED:
                    return state
                failed.append(doc_id)
                status[doc_id] = "failed"
                continue
            processed.append(doc_id)
            chunk_ids.extend(chunks)
            status[doc_id] = "processed"
        state = state.model_copy(
            update={
                "processed_document_ids": processed,
                "failed_document_ids": failed,
                "chunk_ids": chunk_ids,
                "processing_status": status,
            }
        )
        return WorkflowStateManager.transition(state, WorkflowStage.EXTRACTING)

    async def evidence_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        state = WorkflowStateManager.transition(state, WorkflowStage.EXTRACTING)
        if (
            self._retriever is None
            or self._claim_extractor is None
            or self._evidence_extractor is None
        ):
            return WorkflowStateManager.transition(state, WorkflowStage.SYNTHESIZING)
        claims = list(state.claims)
        evidence_items = list(state.evidence_items)
        for task in state.tasks:
            if task.task_type != TaskType.EXTRACT:
                continue
            state, retrieval, failed_operation = await self._execute_external(
                state, WorkflowStage.EXTRACTING, self._retriever.retrieve, task.title,
                terminal_on_failure=False,
            )
            if failed_operation:
                if state.current_stage == WorkflowStage.BUDGET_EXCEEDED:
                    return state
                continue
            chunks = retrieval.chunks
            state, extraction, failed_operation = await self._execute_external(
                state, WorkflowStage.EXTRACTING, self._claim_extractor.extract,
                chunks, task.title, budget_operation="llm", terminal_on_failure=False,
            )
            if failed_operation:
                if state.current_stage == WorkflowStage.BUDGET_EXCEEDED:
                    return state
                continue
            claims.extend(extraction.claims)
            for claim in extraction.claims:
                state, evidence, failed_operation = await self._execute_external(
                    state, WorkflowStage.EXTRACTING, self._evidence_extractor.extract,
                    claim, chunks, budget_operation="llm", terminal_on_failure=False,
                )
                if failed_operation:
                    if state.current_stage == WorkflowStage.BUDGET_EXCEEDED:
                        return state
                    continue
                evidence_items.extend(evidence.evidence)
        state = state.model_copy(
            update={"claims": claims, "evidence_items": evidence_items}
        )
        return WorkflowStateManager.transition(state, WorkflowStage.SYNTHESIZING)

    async def synthesis_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        state = WorkflowStateManager.transition(state, WorkflowStage.SYNTHESIZING)
        if self._llm is None:
            state = state.model_copy(update={"completed_at": datetime.now(UTC)})
            return WorkflowStateManager.transition(state, WorkflowStage.COMPLETED)
        state, response, failed = await self._execute_external(
            state, WorkflowStage.SYNTHESIZING,
            asyncio.to_thread,
            self._llm.complete, self._build_synthesis_prompt(state), SynthesisResponse,
            budget_operation="llm",
        )
        if failed:
            return state
        summary = response.summary if isinstance(response, SynthesisResponse) else ""
        if summary and self._summary_saver is not None:
            state, _, _ = await self._execute_external(
                state, WorkflowStage.SYNTHESIZING, self._summary_saver,
                state.research_id, summary, terminal_on_failure=False,
            )
        state = state.model_copy(update={"completed_at": datetime.now(UTC)})
        return WorkflowStateManager.transition(state, WorkflowStage.COMPLETED)

    @staticmethod
    def _build_synthesis_prompt(state) -> str:
        lines = [f"- {claim.text}" for claim in state.claims]
        body = "\n".join(lines) or "(none)"
        return (
            "Summarize the research findings from these claims.\n"
            f"Claims:\n{body}\n"
            "Return a JSON object with a 'summary' field."
        )

    # --- terminal nodes ------------------------------------------------------

    async def complete_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        return WorkflowStateManager.transition(state, WorkflowStage.COMPLETED)

    async def budget_exceeded_node(
        self, state: ResearchWorkflowState
    ) -> ResearchWorkflowState:
        return WorkflowStateManager.transition(state, WorkflowStage.BUDGET_EXCEEDED)

    async def failed_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        return WorkflowStateManager.transition(state, WorkflowStage.FAILED)
