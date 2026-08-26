"""Integration tests for RDA-036 retry behavior in workflow nodes."""

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

from app.schemas.search import NormalizedSearchResult
from app.services.orchestration.nodes import ResearchNodes
from app.services.workflow.retry_handler import RetryPolicy
from app.services.workflow.state import ResearchWorkflowState, WorkflowStage
from app.services.workflow.state_manager import WorkflowStateManager


class _FlakySearch:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def search(self, query: str):
        self.calls += 1
        if self.calls <= self.failures:
            raise asyncio.TimeoutError("search timeout")
        return [NormalizedSearchResult(source="test", title=query)]


def _state(**updates) -> ResearchWorkflowState:
    return WorkflowStateManager.create_initial_state(uuid.uuid4()).model_copy(
        update={"search_queries": ["query"], **updates}
    )


def test_search_records_retry_and_continues_after_transient_failure() -> None:
    search = _FlakySearch(failures=2)
    nodes = ResearchNodes(search=search)

    with patch("asyncio.sleep", new_callable=AsyncMock) as sleep:
        result = asyncio.run(nodes.search_node(_state()))

    assert search.calls == 3
    assert result.current_stage == WorkflowStage.SELECTING
    assert result.retry_count == 2
    assert result.search_results[0].title == "query"
    assert result.errors[-1].context["retries"] == 2
    assert sleep.await_count == 2


def test_search_transitions_to_failed_after_retry_exhaustion() -> None:
    search = _FlakySearch(failures=10)
    nodes = ResearchNodes(
        search=search,
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0),
    )

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = asyncio.run(nodes.search_node(_state()))

    assert search.calls == 3
    assert result.current_stage == WorkflowStage.FAILED
    assert result.retry_count == 2
    assert result.errors[-1].context["attempts"] == 3


def test_global_retry_limit_prevents_external_call() -> None:
    search = _FlakySearch(failures=0)
    nodes = ResearchNodes(search=search)

    result = asyncio.run(nodes.search_node(_state(retry_count=10)))

    assert search.calls == 0
    assert result.current_stage == WorkflowStage.FAILED
    assert result.errors[-1].context["global_limit"] == 10