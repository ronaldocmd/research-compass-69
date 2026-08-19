"""Business rules for research plans (RDA-031).

Generates a plan through ResearchPlanner (RDA-030), persists it and replaces
any previous plan for the same Research. Planning errors propagate to the
caller so nothing is saved on an invalid plan.
"""

import asyncio
import uuid

from sqlalchemy.orm import Session

from app.models.plan import PlanStatus, PlanTaskRecord, ResearchPlanRecord
from app.repositories.plan_task_repository import PlanTaskRepository
from app.repositories.research_plan_repository import ResearchPlanRepository
from app.repositories.research_repository import ResearchRepository
from app.services.planning.planner import ResearchPlanner
from app.services.planning.schemas import ResearchPlanInput
from app.services.research_service import ResearchNotFoundError


class ResearchPlanNotFoundError(Exception):
    """Raised when a Research has no plan yet."""

    def __init__(self, research_id: uuid.UUID) -> None:
        super().__init__(f"No research plan found for research {research_id}")
        self.research_id = research_id


class ResearchPlanService:
    def __init__(self, db: Session, planner: ResearchPlanner | None = None) -> None:
        self.db = db
        self._research_repo = ResearchRepository(db)
        self._plan_repo = ResearchPlanRepository(db)
        self._task_repo = PlanTaskRepository(db)
        self._planner = planner if planner is not None else ResearchPlanner()

    def create_plan(
        self,
        research_id: uuid.UUID,
        *,
        language: str = "en",
        depth: str = "standard",
        sources: list[str] | None = None,
    ) -> ResearchPlanRecord:
        """Generate and persist a plan for ``research_id``.

        Replaces any existing plan for the research. Raises
        ResearchNotFoundError, InvalidPlanError or PlanningError without
        persisting anything on failure.
        """
        research = self._research_repo.get(research_id)
        if research is None:
            raise ResearchNotFoundError(research_id)

        plan_input = ResearchPlanInput(
            research_id=research_id,
            objective=research.objective,
            question=research.question,
            language=language,
            depth=depth,
            sources=sources or [],
        )

        # The planner is async (RDA-030); the service/endpoints are sync, so
        # bridge with asyncio.run (no event loop is running in this thread).
        plan = asyncio.run(self._planner.plan(plan_input))

        self._plan_repo.delete_by_research_id(research_id)
        record = self._plan_repo.create(
            research_id=research_id, status=PlanStatus.CREATED
        )
        tasks_data = [
            {
                "plan_id": record.id,
                "title": task.title,
                "description": task.description,
                "priority": task.priority,
                "task_type": task.task_type,
                "status": task.status,
                "order": index,
            }
            for index, task in enumerate(plan.tasks)
        ]
        self._task_repo.bulk_create(tasks_data)
        self.db.refresh(record)
        return record

    def get_plan(self, research_id: uuid.UUID) -> ResearchPlanRecord:
        plan = self._plan_repo.get_by_research_id(research_id)
        if plan is None:
            raise ResearchPlanNotFoundError(research_id)
        return plan

    def list_tasks(self, research_id: uuid.UUID) -> list[PlanTaskRecord]:
        plan = self.get_plan(research_id)
        return self._task_repo.list_by_plan_id(plan.id)
