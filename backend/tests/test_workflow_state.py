"""Tests for ResearchWorkflowState and WorkflowStateManager (RDA-032)."""

import uuid
from datetime import UTC, datetime

import pytest

from app.schemas.search import NormalizedSearchResult
from app.services.claims.schemas import Claim
from app.services.evidence.schemas import Evidence, EvidenceStatus
from app.services.planning.schemas import PlanTask, TaskStatus, TaskType
from app.services.workflow.exceptions import WorkflowStateError
from app.services.workflow.state import (
    BudgetState,
    ErrorSeverity,
    ResearchWorkflowState,
    WorkflowError,
    WorkflowStage,
)
from app.services.workflow.state_manager import WorkflowStateManager


def test_initial_state_created_correctly() -> None:
    research_id = uuid.uuid4()

    state = WorkflowStateManager.create_initial_state(research_id)

    assert state.research_id == research_id
    assert isinstance(state.execution_id, uuid.UUID)
    assert state.current_stage == WorkflowStage.IDLE
    assert state.plan_id is None
    assert state.tasks == []
    assert state.search_queries == []
    assert state.search_results == []
    assert state.selected_documents == []
    assert state.processed_document_ids == []
    assert state.failed_document_ids == []
    assert state.processing_status == {}
    assert state.chunk_ids == []
    assert state.claims == []
    assert state.evidence_items == []
    assert state.errors == []
    assert state.retry_count == 0
    assert state.budget == BudgetState()
    assert state.started_at is None
    assert state.updated_at is not None
    assert state.completed_at is None
    assert state.checkpointed_at is None


def test_budget_defaults() -> None:
    budget = BudgetState()

    assert budget.llm_calls == 0
    assert budget.total_tokens == 0
    assert budget.search_calls == 0
    assert budget.processing_operations == 0
    assert budget.estimated_cost_usd == 0.0
    assert budget.max_llm_calls == 50
    assert budget.max_search_calls == 20
    assert budget.max_cost_usd == 5.0
    assert budget.is_exceeded is False


def test_transition_returns_new_state_without_mutating() -> None:
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())

    new_state = WorkflowStateManager.transition(state, WorkflowStage.SEARCHING)

    assert new_state is not state
    assert new_state.current_stage == WorkflowStage.SEARCHING
    assert state.current_stage == WorkflowStage.IDLE


def test_add_error_returns_new_state() -> None:
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())
    error = WorkflowError(
        error_id=uuid.uuid4(),
        stage=WorkflowStage.SEARCHING,
        message="boom",
        severity=ErrorSeverity.TRANSIENT,
        timestamp=datetime.now(UTC),
        retryable=True,
        context={"provider": "openalex"},
    )

    new_state = WorkflowStateManager.add_error(state, error)

    assert len(new_state.errors) == 1
    assert new_state.errors[0].message == "boom"
    assert state.errors == []


def test_empty_state_serializes() -> None:
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())

    restored = WorkflowStateManager.from_json(WorkflowStateManager.to_json(state))

    assert restored == state


def test_serialization_round_trip_preserves_fields() -> None:
    now = datetime.now(UTC)
    chunk_id = uuid.uuid4()
    document_id = uuid.uuid4()
    claim_id = uuid.uuid4()
    evidence_id = uuid.uuid4()

    state = ResearchWorkflowState(
        research_id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
        current_stage=WorkflowStage.EXTRACTING,
        plan_id=uuid.uuid4(),
        tasks=[
            PlanTask(
                task_id=uuid.uuid4(),
                title="search",
                description="d",
                priority=1,
                task_type=TaskType.SEARCH,
                status=TaskStatus.PENDING,
            )
        ],
        search_queries=["llm review"],
        search_results=[NormalizedSearchResult(source="openalex", title="A paper")],
        selected_documents=[document_id],
        processed_document_ids=[document_id],
        failed_document_ids=[],
        processing_status={document_id: "done"},
        chunk_ids=[chunk_id],
        claims=[
            Claim(
                claim_id=claim_id,
                text="a claim",
                chunk_ids=[chunk_id],
                document_id=document_id,
                page_number=1,
                extracted_at=now,
            )
        ],
        evidence_items=[
            Evidence(
                evidence_id=evidence_id,
                claim_id=claim_id,
                text="evidence",
                chunk_id=chunk_id,
                document_id=document_id,
                page_number=1,
                status=EvidenceStatus.SUPPORTED,
                extracted_at=now,
            )
        ],
        errors=[
            WorkflowError(
                error_id=uuid.uuid4(),
                stage=WorkflowStage.EXTRACTING,
                message="m",
                severity=ErrorSeverity.PROCESSING,
                timestamp=now,
                retryable=False,
                context={"x": 1},
            )
        ],
        retry_count=2,
        budget=BudgetState(
            llm_calls=3,
            total_tokens=150,
            search_calls=1,
            processing_operations=2,
            estimated_cost_usd=0.1,
            is_exceeded=False,
        ),
        started_at=now,
        updated_at=now,
        completed_at=None,
        checkpointed_at=None,
    )

    restored = WorkflowStateManager.from_json(WorkflowStateManager.to_json(state))

    assert restored == state


def test_from_json_invalid_raises_workflow_state_error() -> None:
    with pytest.raises(WorkflowStateError):
        WorkflowStateManager.from_json("not valid json")
