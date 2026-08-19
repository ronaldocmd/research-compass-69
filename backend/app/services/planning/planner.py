"""ResearchPlanner (RDA-030).

    ResearchPlanInput
        -> ResearchPlanner.plan (async)
            -> LLMProvider.complete(prompt, ResearchPlanResponse)
            -> validation + conversion to PlanTask
            -> ResearchPlan

It only plans: it never executes the tasks (that is RDA-033). The underlying
LLMProvider is synchronous, so the blocking call is offloaded with
``asyncio.to_thread`` to keep ``plan`` asynchronous as required by the
orchestration layer.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from app.core.config import settings
from app.services.llm.exceptions import InvalidLLMResponseError, LLMProviderError
from app.services.llm.openai_provider import OpenAILLMProvider
from app.services.llm.provider import LLMProvider
from app.services.planning.exceptions import InvalidPlanError, PlanningError
from app.services.planning.schemas import (
    PlanTask,
    PlanTaskDraft,
    ResearchPlan,
    ResearchPlanInput,
    ResearchPlanResponse,
    TaskStatus,
    TaskType,
)


def build_planning_prompt(
    plan_input: ResearchPlanInput, *, min_tasks: int, max_tasks: int
) -> str:
    """Build the prompt that asks the LLM to produce a research plan."""
    sources = ", ".join(plan_input.sources) if plan_input.sources else "none"
    return "\n".join(
        [
            "You are an academic research agent.",
            "Create a detailed research plan for:",
            "",
            f"Objective: {plan_input.objective}",
            f"Question: {plan_input.question}",
            f"Language: {plan_input.language}",
            f"Depth: {plan_input.depth}",
            f"Available sources: {sources}",
            "",
            f"Return a plan with between {min_tasks} and {max_tasks} prioritized tasks.",
            "Each task must have: title, description, priority (1-5, 1 is highest),",
            "and task_type (one of: SEARCH, PROCESS, EXTRACT, VALIDATE, SYNTHESIZE).",
            "A deeper depth should produce more, more detailed tasks.",
        ]
    )


class ResearchPlanner:
    """Turns a research question into a prioritized plan of tasks."""

    def __init__(
        self,
        llm: LLMProvider | None = None,
        *,
        min_tasks: int | None = None,
        max_tasks: int | None = None,
    ) -> None:
        self._llm = llm if llm is not None else OpenAILLMProvider()
        self._min_tasks = (
            min_tasks if min_tasks is not None else settings.PLANNING_MIN_TASKS
        )
        self._max_tasks = (
            max_tasks if max_tasks is not None else settings.PLANNING_MAX_TASKS
        )

    async def plan(self, plan_input: ResearchPlanInput) -> ResearchPlan:
        """Generate a ResearchPlan for ``plan_input``.

        Raises:
            InvalidPlanError: When the LLM returns an invalid or out-of-bounds plan.
            PlanningError: When the LLM provider fails (e.g. timeout).
        """
        prompt = build_planning_prompt(
            plan_input, min_tasks=self._min_tasks, max_tasks=self._max_tasks
        )

        try:
            response = await asyncio.to_thread(
                self._llm.complete, prompt, ResearchPlanResponse
            )
        except InvalidLLMResponseError as exc:
            raise InvalidPlanError(f"LLM returned an invalid plan: {exc}") from exc
        except LLMProviderError as exc:
            raise PlanningError(f"Planning failed: {exc}") from exc

        if not isinstance(response, ResearchPlanResponse):
            raise InvalidPlanError(
                f"Expected ResearchPlanResponse, got {type(response).__name__}"
            )

        tasks = [self._build_task(draft) for draft in response.tasks]
        if len(tasks) < self._min_tasks:
            raise InvalidPlanError(
                f"Plan has {len(tasks)} tasks; at least {self._min_tasks} are required"
            )
        if len(tasks) > self._max_tasks:
            raise InvalidPlanError(
                f"Plan has {len(tasks)} tasks; at most {self._max_tasks} are allowed"
            )

        return ResearchPlan(
            plan_id=uuid.uuid4(),
            research_id=plan_input.research_id,
            tasks=tasks,
            created_at=datetime.now(UTC),
        )

    @staticmethod
    def _build_task(draft: PlanTaskDraft) -> PlanTask:
        if not draft.title or not draft.title.strip():
            raise InvalidPlanError("Plan task has an empty title")
        if not draft.description or not draft.description.strip():
            raise InvalidPlanError("Plan task has an empty description")
        if not 1 <= draft.priority <= 5:
            raise InvalidPlanError(
                f"Plan task priority must be between 1 and 5, got {draft.priority}"
            )
        try:
            task_type = TaskType(draft.task_type)
        except ValueError as exc:
            allowed = [t.value for t in TaskType]
            raise InvalidPlanError(
                f"Unknown task_type {draft.task_type!r}; expected one of {allowed}"
            ) from exc

        return PlanTask(
            task_id=uuid.uuid4(),
            title=draft.title,
            description=draft.description,
            priority=draft.priority,
            task_type=task_type,
            status=TaskStatus.PENDING,
        )
