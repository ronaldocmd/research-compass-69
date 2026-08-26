"""Tests for RDA-037 budget enforcement and accounting."""

import asyncio
import uuid

import pytest

from app.schemas.search import NormalizedSearchResult
from app.services.orchestration.nodes import ResearchNodes
from app.services.workflow.budget_guard import (
    BudgetConfig,
    BudgetExceededError,
    BudgetGuard,
)
from app.services.workflow.state_manager import WorkflowStateManager


class _Search:
    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str):
        self.calls += 1
        return [NormalizedSearchResult(source="test", title=query)]


class _Checkpoints:
    def __init__(self) -> None:
        self.saved = []

    async def save(self, state) -> None:
        self.saved.append(state)


def test_cost_is_calculated_from_configurable_prices() -> None:
    guard = BudgetGuard(
        BudgetConfig(
            cost_per_llm_call_usd=0.1,
            cost_per_search_call_usd=0.02,
            cost_per_1k_tokens_usd=0.5,
        )
    )
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())

    state = guard.record_llm_call(state, tokens_used=2000)
    state = guard.record_search_call(state)
    state = guard.record_processing(state)

    assert state.budget.llm_calls == 1
    assert state.budget.search_calls == 1
    assert state.budget.processing_operations == 1
    assert state.budget.total_tokens == 2000
    assert state.budget.estimated_cost_usd == pytest.approx(1.12)


def test_llm_limit_is_rejected_and_budget_is_marked() -> None:
    guard = BudgetGuard(BudgetConfig(max_llm_calls=1))
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())
    state = guard.record_llm_call(state)

    assert guard.is_exceeded(state) is True
    with pytest.raises(BudgetExceededError, match="llm"):
        guard.check_before_llm_call(state)


def test_cost_limit_is_rejected() -> None:
    guard = BudgetGuard(BudgetConfig(max_cost_usd=0.01))
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())
    state = guard.record_llm_call(state)

    with pytest.raises(BudgetExceededError, match="cost_usd"):
        guard.check_before_search(state)


def test_budget_allows_operations_under_limits() -> None:
    guard = BudgetGuard(BudgetConfig(max_llm_calls=2, max_search_calls=2))
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())

    guard.check_before_llm_call(state)
    guard.check_before_search(state)
    assert guard.is_exceeded(state) is False


def test_node_records_budget_error_and_saves_checkpoint() -> None:
    search = _Search()
    checkpoints = _Checkpoints()
    nodes = ResearchNodes(
        search=search,
        budget_config=BudgetConfig(max_search_calls=1),
        checkpoint_manager=checkpoints,
    )
    state = WorkflowStateManager.create_initial_state(uuid.uuid4()).model_copy(
        update={"search_queries": ["first", "second"]}
    )

    result = asyncio.run(nodes.search_node(state))

    assert search.calls == 1
    assert result.current_stage.value == "BUDGET_EXCEEDED"
    assert result.budget.is_exceeded is True
    assert result.errors
    assert checkpoints.saved and checkpoints.saved[-1].current_stage.value == "BUDGET_EXCEEDED"