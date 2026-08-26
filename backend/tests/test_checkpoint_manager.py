"""Tests for workflow checkpoint persistence (RDA-035)."""

import asyncio
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Research
from app.models.workflow_checkpoint import WorkflowCheckpoint
from app.services.workflow.checkpoint_manager import CheckpointManager
from app.services.workflow.state import ResearchWorkflowState, WorkflowStage


def test_checkpoint_manager_saves_and_restores_state() -> None:
    asyncio.run(_assert_checkpoint_persistence())


async def _assert_checkpoint_persistence() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    research_id = uuid.uuid4()
    execution_id = uuid.uuid4()

    with Session(engine) as db:
        db.add(
            Research(
                id=research_id,
                title="Checkpoint test",
                objective="Persist state",
                question="Does it resume?",
            )
        )
        db.commit()
        manager = CheckpointManager(db)
        state = ResearchWorkflowState(
            research_id=research_id,
            execution_id=execution_id,
            current_stage=WorkflowStage.SEARCH,
            search_results=[{"title": "A", "score": 0.9}],
            selected_ids=[str(uuid.uuid4())],
        )
        first = await manager.save(state)

        state.current_stage = WorkflowStage.SELECTING
        second = await manager.save(state)

        restored = await manager.load_latest(str(execution_id))
        search_checkpoint = await manager.load_by_stage(str(execution_id), WorkflowStage.SEARCH)
        checkpoints = await manager.list_checkpoints(str(execution_id))
        latest_flags = db.scalars(
            select(WorkflowCheckpoint.is_latest).where(
                WorkflowCheckpoint.execution_id == execution_id
            )
        ).all()

    assert first.stage == WorkflowStage.SEARCH
    assert second.stage == WorkflowStage.SELECTING
    assert restored is not None
    assert restored.current_stage == WorkflowStage.SELECTING
    assert restored.search_results == [{"title": "A", "score": 0.9}]
    assert search_checkpoint is not None
    assert search_checkpoint.current_stage == WorkflowStage.SEARCH
    assert len(checkpoints) == 2
    assert latest_flags.count(True) == 1