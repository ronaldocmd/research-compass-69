"""WorkflowStateManager (RDA-032).

Pure, immutable helpers to create, transition, update and (de)serialize the
research workflow state. Every mutation returns a NEW state object; the
original is never modified in place.
"""

import uuid
from datetime import UTC, datetime

from pydantic import ValidationError

from app.services.workflow.exceptions import WorkflowStateError
from app.services.workflow.state import ResearchWorkflowState, WorkflowError, WorkflowStage


class WorkflowStateManager:
    """Creates and manipulates ResearchWorkflowState snapshots."""

    @staticmethod
    def create_initial_state(research_id: uuid.UUID) -> ResearchWorkflowState:
        """Return a fresh IDLE state for ``research_id``."""
        now = datetime.now(UTC)
        return ResearchWorkflowState(
            research_id=research_id,
            execution_id=uuid.uuid4(),
            current_stage=WorkflowStage.IDLE,
            updated_at=now,
        )

    @staticmethod
    def transition(
        state: ResearchWorkflowState, new_stage: WorkflowStage
    ) -> ResearchWorkflowState:
        """Return a copy of ``state`` moved to ``new_stage``."""
        return state.model_copy(
            update={"current_stage": new_stage, "updated_at": datetime.now(UTC)}
        )

    @staticmethod
    def add_error(
        state: ResearchWorkflowState, error: WorkflowError
    ) -> ResearchWorkflowState:
        """Return a copy of ``state`` with ``error`` appended."""
        return state.model_copy(
            update={"errors": [*state.errors, error], "updated_at": datetime.now(UTC)}
        )

    @staticmethod
    def to_json(state: ResearchWorkflowState) -> str:
        """Serialize ``state`` to a JSON string."""
        return state.model_dump_json()

    @staticmethod
    def from_json(json_str: str) -> ResearchWorkflowState:
        """Deserialize a JSON string back into a ResearchWorkflowState."""
        try:
            return ResearchWorkflowState.model_validate_json(json_str)
        except ValidationError as exc:
            raise WorkflowStateError(f"Invalid workflow state JSON: {exc}") from exc
