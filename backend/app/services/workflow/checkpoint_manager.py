"""Persistence and restoration of workflow checkpoints."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.workflow_checkpoint import WorkflowCheckpoint
from app.services.workflow.state import ResearchWorkflowState, WorkflowStage


class CheckpointManager:
    def __init__(self, db: Session) -> None:
        self.db = db

    async def save(self, state: ResearchWorkflowState) -> WorkflowCheckpoint:
        """Save the current state and mark earlier checkpoints as stale."""
        self.db.execute(
            update(WorkflowCheckpoint)
            .where(WorkflowCheckpoint.execution_id == state.execution_id)
            .values(is_latest=False)
        )
        checkpoint = WorkflowCheckpoint(
            research_id=state.research_id,
            execution_id=state.execution_id,
            stage=state.current_stage,
            state_json=state.model_dump_json(),
            is_latest=True,
        )
        self.db.add(checkpoint)
        self.db.commit()
        self.db.refresh(checkpoint)
        return checkpoint

    async def load_latest(self, execution_id: str) -> ResearchWorkflowState | None:
        """Load the most recent checkpoint for an execution."""
        checkpoint = self.db.scalar(
            select(WorkflowCheckpoint)
            .where(
                WorkflowCheckpoint.execution_id == uuid.UUID(execution_id),
                WorkflowCheckpoint.is_latest.is_(True),
            )
            .order_by(WorkflowCheckpoint.checkpoint_at.desc(), WorkflowCheckpoint.id.desc())
        )
        return self._restore(checkpoint)

    async def load_by_stage(
        self, execution_id: str, stage: WorkflowStage
    ) -> ResearchWorkflowState | None:
        """Load the newest checkpoint at a particular stage."""
        checkpoint = self.db.scalar(
            select(WorkflowCheckpoint)
            .where(
                WorkflowCheckpoint.execution_id == uuid.UUID(execution_id),
                WorkflowCheckpoint.stage == stage,
            )
            .order_by(WorkflowCheckpoint.checkpoint_at.desc(), WorkflowCheckpoint.id.desc())
        )
        return self._restore(checkpoint)

    async def list_checkpoints(self, execution_id: str) -> list[WorkflowCheckpoint]:
        """List checkpoints from oldest to newest."""
        return list(
            self.db.scalars(
                select(WorkflowCheckpoint)
                .where(WorkflowCheckpoint.execution_id == uuid.UUID(execution_id))
                .order_by(WorkflowCheckpoint.checkpoint_at.asc(), WorkflowCheckpoint.id.asc())
            )
        )

    @staticmethod
    def _restore(checkpoint: WorkflowCheckpoint | None) -> ResearchWorkflowState | None:
        if checkpoint is None:
            return None
        return ResearchWorkflowState.model_validate_json(checkpoint.state_json)