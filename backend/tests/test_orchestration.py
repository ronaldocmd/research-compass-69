"""Tests for the research workflow orchestration (RDA-033).

No real LLM/search calls: the graph is driven with the stage-transition
skeleton nodes (which need no services) and with fakes where delegation is
exercised.
"""

import asyncio
import types
import uuid
from datetime import UTC, datetime

import pytest

from app.schemas.search import NormalizedSearchResult
from app.services.orchestration.exceptions import OrchestrationError
from app.services.orchestration.graph import build_graph, route_after_synthesis
from app.services.orchestration.nodes import ResearchNodes
from app.services.orchestration.orchestrator import ResearchOrchestrator
from app.services.workflow.state import (
    ErrorSeverity,
    ResearchWorkflowState,
    WorkflowError,
    WorkflowStage,
)
from app.services.workflow.state_manager import WorkflowStateManager


def _run(graph, state) -> ResearchWorkflowState:
    result = asyncio.run(graph.ainvoke(state))
    return ResearchWorkflowState.model_validate(result)


def _fake_nodes(calls):
    def make(name):
        async def node(state):
            calls.append(name)
            return state

        return node

    return types.SimpleNamespace(
        planner_node=make("planner"),
        search_node=make("search"),
        process_node=make("process"),
        evidence_node=make("evidence"),
        synthesis_node=make("synthesis"),
        complete_node=make("complete"),
        budget_exceeded_node=make("budget_exceeded"),
        failed_node=make("failed"),
    )


def _error(severity: ErrorSeverity) -> WorkflowError:
    return WorkflowError(
        error_id=uuid.uuid4(),
        stage=WorkflowStage.SEARCHING,
        message="boom",
        severity=severity,
        timestamp=datetime.now(UTC),
        retryable=False,
        context={},
    )


# --- route_after_synthesis ---------------------------------------------------


def test_route_completes_by_default() -> None:
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())
    assert route_after_synthesis(state) == "complete"


def test_route_budget_exceeded() -> None:
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())
    state = state.model_copy(
        update={"budget": state.budget.model_copy(update={"is_exceeded": True})}
    )
    assert route_after_synthesis(state) == "budget_exceeded"


def test_route_failed_on_permanent_error() -> None:
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())
    state = WorkflowStateManager.add_error(state, _error(ErrorSeverity.PERMANENT))
    assert route_after_synthesis(state) == "failed"


def test_route_ignores_transient_error() -> None:
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())
    state = WorkflowStateManager.add_error(state, _error(ErrorSeverity.TRANSIENT))
    assert route_after_synthesis(state) == "complete"


# --- graph flow --------------------------------------------------------------


def test_workflow_traverses_stages_in_order() -> None:
    calls: list[str] = []
    graph = build_graph(_fake_nodes(calls))

    _run(graph, WorkflowStateManager.create_initial_state(uuid.uuid4()))

    assert calls == ["planner", "search", "process", "evidence", "synthesis", "complete"]


def test_workflow_reaches_completed() -> None:
    graph = build_graph(ResearchNodes())

    final = _run(graph, WorkflowStateManager.create_initial_state(uuid.uuid4()))

    assert final.current_stage == WorkflowStage.COMPLETED


def test_workflow_budget_exceeded() -> None:
    graph = build_graph(ResearchNodes())
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())
    state = state.model_copy(
        update={"budget": state.budget.model_copy(update={"is_exceeded": True})}
    )

    final = _run(graph, state)

    assert final.current_stage == WorkflowStage.BUDGET_EXCEEDED


def test_workflow_failed_on_permanent_error() -> None:
    graph = build_graph(ResearchNodes())
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())
    state = WorkflowStateManager.add_error(state, _error(ErrorSeverity.PERMANENT))

    final = _run(graph, state)

    assert final.current_stage == WorkflowStage.FAILED


def test_search_node_receives_correct_state() -> None:
    class _RecordingSearch:
        def __init__(self) -> None:
            self.received: list[str] = []

        def search(self, query: str):
            self.received.append(query)
            return [NormalizedSearchResult(source="openalex", title=query)]

    search = _RecordingSearch()
    graph = build_graph(ResearchNodes(search=search))
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())
    state = state.model_copy(update={"search_queries": ["q1", "q2"]})

    final = _run(graph, state)

    assert search.received == ["q1", "q2"]
    assert [r.title for r in final.search_results] == ["q1", "q2"]


# --- orchestrator ------------------------------------------------------------


def test_orchestrator_run_and_get_state() -> None:
    orchestrator = ResearchOrchestrator()
    research_id = uuid.uuid4()

    state = asyncio.run(orchestrator.run(research_id))

    assert state.research_id == research_id
    assert state.current_stage == WorkflowStage.COMPLETED

    fetched = asyncio.run(orchestrator.get_state(state.execution_id))
    assert fetched.execution_id == state.execution_id

    by_research = asyncio.run(orchestrator.get_state_by_research(research_id))
    assert by_research.execution_id == state.execution_id


def test_orchestrator_get_state_unknown_raises() -> None:
    orchestrator = ResearchOrchestrator()

    with pytest.raises(OrchestrationError):
        asyncio.run(orchestrator.get_state(uuid.uuid4()))
    with pytest.raises(OrchestrationError):
        asyncio.run(orchestrator.get_state_by_research(uuid.uuid4()))
