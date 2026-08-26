"""ResearchOrchestrator (RDA-033).

Entry point that runs the LangGraph workflow for a research and tracks the
execution state in memory (checkpointing to a store arrives in RDA-035).
"""

import uuid

from app.services.orchestration.exceptions import OrchestrationError
from app.services.orchestration.graph import build_graph
from app.services.orchestration.nodes import ResearchNodes
from app.services.workflow.state import ResearchWorkflowState
from app.services.workflow.state_manager import WorkflowStateManager


class ResearchOrchestrator:
    """Runs the research workflow graph and tracks executions."""

    def __init__(
        self,
        nodes: ResearchNodes | None = None,
        performance_tracker=None,
    ) -> None:
        if nodes is None:
            nodes = ResearchNodes(performance_tracker=performance_tracker)
        self._graph = build_graph(nodes)
        self._states: dict[uuid.UUID, ResearchWorkflowState] = {}
        self._latest_by_research: dict[uuid.UUID, uuid.UUID] = {}

    async def run(self, research_id: uuid.UUID) -> ResearchWorkflowState:
        """Execute the full workflow for ``research_id`` and return the state."""
        initial = WorkflowStateManager.create_initial_state(research_id)
        result = await self._graph.ainvoke(initial)
        state = ResearchWorkflowState.model_validate(result)
        self._states[state.execution_id] = state
        self._latest_by_research[research_id] = state.execution_id
        return state

    async def get_state(self, execution_id: uuid.UUID) -> ResearchWorkflowState:
        """Return the state of a single execution."""
        try:
            return self._states[execution_id]
        except KeyError as exc:
            raise OrchestrationError(f"No execution found for {execution_id}") from exc

    async def get_state_by_research(self, research_id: uuid.UUID) -> ResearchWorkflowState:
        """Return the latest execution state for ``research_id``."""
        try:
            execution_id = self._latest_by_research[research_id]
        except KeyError as exc:
            raise OrchestrationError(f"No execution found for research {research_id}") from exc
        return self._states[execution_id]
