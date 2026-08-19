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

from app.services.llm.exceptions import InvalidLLMResponseError, LLMProviderError
from app.services.planning.exceptions import InvalidPlanError, PlanningError
from app.services.planning.schemas import ResearchPlanInput, TaskType
from app.services.workflow.state import (
    ErrorSeverity,
    ResearchWorkflowState,
    WorkflowError,
    WorkflowStage,
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

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _record_error(state, stage, message, *, severity=ErrorSeverity.PROCESSING, retryable=False):
        error = WorkflowError(
            error_id=uuid.uuid4(),
            stage=stage,
            message=message,
            severity=severity,
            timestamp=datetime.now(UTC),
            retryable=retryable,
            context={},
        )
        return WorkflowStateManager.add_error(state, error)

    @staticmethod
    def _add_llm_calls(state, count=1):
        budget = state.budget.model_copy(
            update={"llm_calls": state.budget.llm_calls + count}
        )
        return state.model_copy(update={"budget": budget})

    @staticmethod
    def _add_search_calls(state, count):
        budget = state.budget.model_copy(
            update={"search_calls": state.budget.search_calls + count}
        )
        return state.model_copy(update={"budget": budget})

    @staticmethod
    def _add_processing_ops(state, count):
        budget = state.budget.model_copy(
            update={"processing_operations": state.budget.processing_operations + count}
        )
        return state.model_copy(update={"budget": budget})

    # --- nodes ---------------------------------------------------------------

    async def planner_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        state = WorkflowStateManager.transition(state, WorkflowStage.PLANNING)
        if self._planner is None or self._research_loader is None:
            return state
        try:
            research = self._research_loader(state.research_id)
        except Exception as exc:
            return self._record_error(
                state, WorkflowStage.PLANNING, f"Failed to load research: {exc}"
            )
        if research is None:
            return self._record_error(
                state, WorkflowStage.PLANNING, "Research not found",
                severity=ErrorSeverity.PERMANENT,
            )
        try:
            plan = await self._planner.plan(
                ResearchPlanInput(
                    research_id=state.research_id,
                    objective=research.objective,
                    question=research.question,
                )
            )
        except (InvalidPlanError, PlanningError) as exc:
            return self._record_error(
                state, WorkflowStage.PLANNING, f"Planning failed: {exc}"
            )
        state = state.model_copy(update={"plan_id": plan.plan_id, "tasks": plan.tasks})
        state = self._add_llm_calls(state)
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
        search_calls = 0
        for query in queries:
            try:
                results.extend(self._search.search(query))
                search_calls += 1
            except Exception as exc:
                state = self._record_error(
                    state, WorkflowStage.SEARCHING, f"Search failed for '{query}': {exc}"
                )
        state = state.model_copy(update={"search_results": results})
        state = self._add_search_calls(state, search_calls)
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
        ops = 0
        for doc_id in state.selected_documents:
            if doc_id in processed or doc_id in failed:
                continue
            try:
                chunks = self._processor(doc_id)
                processed.append(doc_id)
                chunk_ids.extend(chunks)
                status[doc_id] = "processed"
                ops += 1
            except Exception as exc:
                failed.append(doc_id)
                status[doc_id] = "failed"
                state = self._record_error(
                    state, WorkflowStage.PROCESSING, f"Processing {doc_id} failed: {exc}"
                )
        state = state.model_copy(
            update={
                "processed_document_ids": processed,
                "failed_document_ids": failed,
                "chunk_ids": chunk_ids,
                "processing_status": status,
            }
        )
        state = self._add_processing_ops(state, ops)
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
        llm_calls = 0
        for task in state.tasks:
            if task.task_type != TaskType.EXTRACT:
                continue
            try:
                chunks = self._retriever.retrieve(task.title).chunks
                extraction = self._claim_extractor.extract(chunks, task.title)
                llm_calls += 1
                claims.extend(extraction.claims)
                for claim in extraction.claims:
                    evidence_items.extend(
                        self._evidence_extractor.extract(claim, chunks).evidence
                    )
                    llm_calls += 1
            except Exception as exc:
                state = self._record_error(
                    state, WorkflowStage.EXTRACTING, f"Evidence extraction failed: {exc}"
                )
        state = state.model_copy(
            update={"claims": claims, "evidence_items": evidence_items}
        )
        state = self._add_llm_calls(state, llm_calls)
        return WorkflowStateManager.transition(state, WorkflowStage.SYNTHESIZING)

    async def synthesis_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        state = WorkflowStateManager.transition(state, WorkflowStage.SYNTHESIZING)
        if self._llm is None:
            state = state.model_copy(update={"completed_at": datetime.now(UTC)})
            return WorkflowStateManager.transition(state, WorkflowStage.COMPLETED)
        try:
            response = await asyncio.to_thread(
                self._llm.complete, self._build_synthesis_prompt(state), SynthesisResponse
            )
        except (InvalidLLMResponseError, LLMProviderError) as exc:
            return self._record_error(
                state, WorkflowStage.SYNTHESIZING, f"Synthesis failed: {exc}"
            )
        state = self._add_llm_calls(state)
        summary = response.summary if isinstance(response, SynthesisResponse) else ""
        if summary and self._summary_saver is not None:
            try:
                self._summary_saver(state.research_id, summary)
            except Exception as exc:
                state = self._record_error(
                    state, WorkflowStage.SYNTHESIZING, f"Failed to save summary: {exc}"
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
