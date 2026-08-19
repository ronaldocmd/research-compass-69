"""Tests for ResearchPlanner (RDA-030).

The LLMProvider is replaced with a fake in every test: no test performs a
real API call. ``plan`` is async, so each test drives it with asyncio.run.
"""

import asyncio
import uuid

import pytest
from pydantic import ValidationError

from app.services.llm.exceptions import InvalidLLMResponseError, LLMProviderTimeoutError
from app.services.llm.provider import LLMProvider
from app.services.planning.exceptions import InvalidPlanError, PlanningError
from app.services.planning.planner import ResearchPlanner, build_planning_prompt
from app.services.planning.schemas import (
    PlanTaskDraft,
    ResearchPlanInput,
    ResearchPlanResponse,
    TaskStatus,
    TaskType,
)


class _FakeLLMProvider(LLMProvider):
    name = "fake"

    def __init__(self, *, response=None, error=None, model="fake-model") -> None:
        self.model = model
        self._response = response
        self._error = error
        self.prompts: list[str] = []

    def complete(self, prompt, response_model):
        self.prompts.append(prompt)
        if self._error is not None:
            raise self._error
        if self._response is None:
            return response_model(tasks=[])
        return self._response


class _DepthAwareLLMProvider(LLMProvider):
    name = "fake"

    def __init__(self) -> None:
        self.model = "fake-model"

    def complete(self, prompt, response_model):
        n = 8 if "Depth: deep" in prompt else 3
        return response_model(
            tasks=[
                PlanTaskDraft(
                    title=f"Task {i}",
                    description=f"Description {i}",
                    priority=1,
                    task_type="SEARCH",
                )
                for i in range(n)
            ]
        )


def _input(*, depth="standard", objective="Find evidence", question="How does X work?") -> ResearchPlanInput:
    return ResearchPlanInput(
        research_id=uuid.uuid4(),
        objective=objective,
        question=question,
        language="en",
        depth=depth,
        sources=["openalex", "crossref"],
    )


def _draft(*, title="A task", description="Do something", priority=1, task_type="SEARCH") -> PlanTaskDraft:
    return PlanTaskDraft(
        title=title, description=description, priority=priority, task_type=task_type
    )


def _response(tasks) -> ResearchPlanResponse:
    return ResearchPlanResponse(tasks=tasks)


def test_plan_generates_at_least_min_tasks() -> None:
    response = _response([_draft(title=f"Task {i}") for i in range(3)])
    planner = ResearchPlanner(llm=_FakeLLMProvider(response=response))

    plan = asyncio.run(planner.plan(_input()))

    assert len(plan.tasks) == 3
    assert plan.plan_id is not None
    assert plan.created_at is not None


def test_tasks_contain_title_description_priority() -> None:
    response = _response(
        [
            _draft(
                title="Search papers",
                description="Query openalex",
                priority=1,
                task_type="SEARCH",
            ),
            _draft(title="Second task", description="Do more", priority=2, task_type="PROCESS"),
            _draft(title="Third task", description="Do even more", priority=3, task_type="EXTRACT"),
        ]
    )
    planner = ResearchPlanner(llm=_FakeLLMProvider(response=response))

    plan = asyncio.run(planner.plan(_input()))

    task = plan.tasks[0]
    assert task.title == "Search papers"
    assert task.description == "Query openalex"
    assert task.priority == 1
    assert task.task_type == TaskType.SEARCH
    assert task.status == TaskStatus.PENDING
    assert task.task_id is not None


def test_deep_depth_generates_more_tasks_than_basic() -> None:
    planner = ResearchPlanner(llm=_DepthAwareLLMProvider())

    deep = asyncio.run(planner.plan(_input(depth="deep")))
    basic = asyncio.run(planner.plan(_input(depth="basic")))

    assert len(deep.tasks) > len(basic.tasks)


def test_invalid_input_raises_error() -> None:
    with pytest.raises(ValidationError):
        _input(objective="")
    with pytest.raises(ValidationError):
        _input(question="   ")
    with pytest.raises(ValidationError):
        _input(depth="invalid")


def test_llm_invalid_json_rejected() -> None:
    llm = _FakeLLMProvider(error=InvalidLLMResponseError("bad json"))
    planner = ResearchPlanner(llm=llm)

    with pytest.raises(InvalidPlanError):
        asyncio.run(planner.plan(_input()))


def test_llm_timeout_raises_planning_error() -> None:
    llm = _FakeLLMProvider(error=LLMProviderTimeoutError("timeout"))
    planner = ResearchPlanner(llm=llm)

    with pytest.raises(PlanningError):
        asyncio.run(planner.plan(_input()))


def test_too_few_tasks_rejected() -> None:
    response = _response([_draft(), _draft()])  # 2 tasks < 3
    planner = ResearchPlanner(llm=_FakeLLMProvider(response=response))

    with pytest.raises(InvalidPlanError):
        asyncio.run(planner.plan(_input()))


def test_too_many_tasks_rejected() -> None:
    response = _response([_draft(title=f"T{i}") for i in range(11)])  # 11 > 10
    planner = ResearchPlanner(llm=_FakeLLMProvider(response=response))

    with pytest.raises(InvalidPlanError):
        asyncio.run(planner.plan(_input()))


def test_invalid_task_fields_rejected() -> None:
    bad_priority = _response([_draft(priority=0), _draft(), _draft()])
    with pytest.raises(InvalidPlanError):
        asyncio.run(
            ResearchPlanner(llm=_FakeLLMProvider(response=bad_priority)).plan(_input())
        )

    bad_type = _response([_draft(task_type="BOGUS"), _draft(), _draft()])
    with pytest.raises(InvalidPlanError):
        asyncio.run(
            ResearchPlanner(llm=_FakeLLMProvider(response=bad_type)).plan(_input())
        )

    bad_title = _response([_draft(title="  "), _draft(), _draft()])
    with pytest.raises(InvalidPlanError):
        asyncio.run(
            ResearchPlanner(llm=_FakeLLMProvider(response=bad_title)).plan(_input())
        )


def test_prompt_reflects_input() -> None:
    llm = _FakeLLMProvider(response=_response([_draft(), _draft(), _draft()]))
    planner = ResearchPlanner(llm=llm)

    asyncio.run(
        planner.plan(
            _input(objective="My objective", question="My question", depth="deep")
        )
    )

    prompt = llm.prompts[0]
    assert "My objective" in prompt
    assert "My question" in prompt
    assert "Depth: deep" in prompt
    assert "openalex" in prompt


def test_prompt_requests_task_count_bounds() -> None:
    prompt = build_planning_prompt(_input(), min_tasks=3, max_tasks=10)

    assert "between 3 and 10" in prompt
