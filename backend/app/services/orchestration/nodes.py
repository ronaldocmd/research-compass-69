"""Workflow nodes (RDA-033).

Each node receives and returns a ResearchWorkflowState. Nodes are thin
wrappers: business logic lives in the existing services, never here. The
planner/process/evidence/synthesis nodes only transition the stage for now —
their full service wiring is detailed in RDA-034.
"""

from app.services.workflow.state import ResearchWorkflowState, WorkflowStage
from app.services.workflow.state_manager import WorkflowStateManager


class ResearchNodes:
    """Node implementations for the research workflow graph."""

    def __init__(self, *, search=None) -> None:
        self._search = search

    async def planner_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        return WorkflowStateManager.transition(state, WorkflowStage.PLANNING)

    async def search_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        state = WorkflowStateManager.transition(state, WorkflowStage.SEARCHING)
        if self._search is not None:
            results = list(state.search_results)
            for query in state.search_queries:
                results.extend(self._search.search(query))
            state = state.model_copy(update={"search_results": results})
        return state

    async def process_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        return WorkflowStateManager.transition(state, WorkflowStage.PROCESSING)

    async def evidence_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        return WorkflowStateManager.transition(state, WorkflowStage.EXTRACTING)

    async def synthesis_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        return WorkflowStateManager.transition(state, WorkflowStage.SYNTHESIZING)

    async def complete_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        return WorkflowStateManager.transition(state, WorkflowStage.COMPLETED)

    async def budget_exceeded_node(
        self, state: ResearchWorkflowState
    ) -> ResearchWorkflowState:
        return WorkflowStateManager.transition(state, WorkflowStage.BUDGET_EXCEEDED)

    async def failed_node(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        return WorkflowStateManager.transition(state, WorkflowStage.FAILED)
