"""Tests for checkpoint-aware workflow execution (RDA-035)."""

import asyncio
import uuid

import pytest

from app.services.workflow.orchestrator import WorkflowOrchestrator
from app.services.workflow.state import ResearchWorkflowState, WorkflowStage


class InMemoryCheckpoints:
    def __init__(self, restored: ResearchWorkflowState | None = None) -> None:
        self.latest = restored
        self.saved: list[ResearchWorkflowState] = []

    async def load_latest(self, execution_id: str) -> ResearchWorkflowState | None:
        return self.latest

    async def save(self, state: ResearchWorkflowState) -> None:
        self.saved.append(state.model_copy(deep=True))
        self.latest = state.model_copy(deep=True)


def test_restart_continues_after_search_without_repeating_nodes() -> None:
    asyncio.run(_assert_restart_continues_after_search())


async def _assert_restart_continues_after_search() -> None:
    research_id = uuid.uuid4()
    execution_id = uuid.uuid4()
    calls: list[str] = []

    async def planner(state: ResearchWorkflowState) -> ResearchWorkflowState:
        calls.append("planner")
        return state

    async def search(state: ResearchWorkflowState) -> ResearchWorkflowState:
        calls.append("search")
        state.search_results = [{"title": "result"}]
        return state

    async def selecting(state: ResearchWorkflowState) -> ResearchWorkflowState:
        calls.append("selecting")
        return state

    async def noop(state: ResearchWorkflowState) -> ResearchWorkflowState:
        return state

    initial = ResearchWorkflowState(research_id=research_id, execution_id=execution_id)
    checkpoints = InMemoryCheckpoints()
    state = await planner(initial)
    state.current_stage = WorkflowStage.SEARCH
    await checkpoints.save(state)
    state = await search(state)
    state.current_stage = WorkflowStage.SELECTING
    await checkpoints.save(state)
    assert calls == ["planner", "search"]
    assert checkpoints.latest is not None
    assert checkpoints.latest.current_stage == WorkflowStage.SELECTING

    restarted = WorkflowOrchestrator(
        checkpoints,
        {
            WorkflowStage.SELECTING: selecting,
            WorkflowStage.EXTRACTING: noop,
            WorkflowStage.VALIDATING: noop,
            WorkflowStage.COMPLETED: noop,
        },
    )
    result = await restarted.run(initial)

    assert calls == ["planner", "search", "selecting"]
    assert result.search_results == [{"title": "result"}]