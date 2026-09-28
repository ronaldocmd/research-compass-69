"""ResearchOrchestrator (RDA-033).

Entry point that runs the LangGraph workflow for a research and tracks the
execution state in memory (checkpointing to a store arrives in RDA-035).
"""

import logging
import uuid
from datetime import UTC, datetime

from app.services.orchestration.exceptions import OrchestrationError
from app.services.orchestration.graph import build_graph
from app.services.orchestration.nodes import ResearchNodes
from app.services.workflow.state import (
    ErrorSeverity,
    ResearchWorkflowState,
    WorkflowError,
    WorkflowStage,
)
from app.services.workflow.state_manager import WorkflowStateManager

logger = logging.getLogger(__name__)


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

    async def run(
        self, research_id: uuid.UUID, *, focus: str | None = None
    ) -> ResearchWorkflowState:
        """Execute the full workflow for ``research_id`` and return the state.

        The state is registered before the first node runs and refreshed
        after every node, so ``get_state_by_research`` reports live progress
        instead of 404 until the whole pipeline finishes. An unexpected node
        exception is recorded as a FAILED state rather than escaping without
        any trace of the execution.
        """
        initial = WorkflowStateManager.create_initial_state(research_id)
        if focus:
            initial = initial.model_copy(update={"research_focus": focus})
        self._states[initial.execution_id] = initial
        self._latest_by_research[research_id] = initial.execution_id
        latest = initial
        try:
            async for snapshot in self._graph.astream(initial, stream_mode="values"):
                latest = ResearchWorkflowState.model_validate(snapshot)
                self._states[initial.execution_id] = latest
        except Exception as exc:
            logger.exception("Workflow crashed for research %s", research_id)
            error = WorkflowError(
                error_id=uuid.uuid4(),
                stage=latest.current_stage,
                message=f"Unhandled workflow error: {exc}",
                severity=ErrorSeverity.PERMANENT,
                timestamp=datetime.now(UTC),
                retryable=False,
            )
            latest = WorkflowStateManager.transition(
                WorkflowStateManager.add_error(latest, error), WorkflowStage.FAILED
            )
            self._states[initial.execution_id] = latest
        return latest

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
