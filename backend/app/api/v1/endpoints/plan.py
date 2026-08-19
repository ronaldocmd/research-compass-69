"""REST endpoints for research planning (RDA-031).

Mounted under /researches so the routes read:
    POST   /researches/{research_id}/plan
    GET    /researches/{research_id}/plan
    GET    /researches/{research_id}/plan/tasks
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.plan import PlanTaskRecord, ResearchPlanRecord
from app.schemas.plan import PlanOut, PlanRequest, PlanTaskOut
from app.services.planning.exceptions import InvalidPlanError, PlanningError
from app.services.planning.planner import ResearchPlanner
from app.services.research_plan_service import ResearchPlanNotFoundError, ResearchPlanService
from app.services.research_service import ResearchNotFoundError

router = APIRouter()


def _planner() -> ResearchPlanner:
    """Planner factory dependency (overridable in tests)."""
    return ResearchPlanner()


def _service(
    db: Session = Depends(get_db), planner: ResearchPlanner = Depends(_planner)
) -> ResearchPlanService:
    return ResearchPlanService(db, planner=planner)


def _to_plan_out(plan: ResearchPlanRecord, tasks: list[PlanTaskRecord]) -> PlanOut:
    return PlanOut(
        id=plan.id,
        research_id=plan.research_id,
        status=plan.status,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        tasks=[PlanTaskOut.model_validate(task) for task in tasks],
    )


@router.post(
    "/{research_id}/plan",
    response_model=PlanOut,
    status_code=status.HTTP_201_CREATED,
)
def create_plan(
    research_id: uuid.UUID,
    payload: PlanRequest,
    service: ResearchPlanService = Depends(_service),
) -> PlanOut:
    try:
        record = service.create_plan(
            research_id,
            language=payload.language,
            depth=payload.depth,
            sources=payload.sources,
        )
    except ResearchNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidPlanError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except PlanningError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    tasks = service.list_tasks(research_id)
    return _to_plan_out(record, tasks)


@router.get("/{research_id}/plan", response_model=PlanOut)
def get_plan(
    research_id: uuid.UUID,
    service: ResearchPlanService = Depends(_service),
) -> PlanOut:
    try:
        plan = service.get_plan(research_id)
        tasks = service.list_tasks(research_id)
    except ResearchPlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_plan_out(plan, tasks)


@router.get("/{research_id}/plan/tasks", response_model=list[PlanTaskOut])
def list_plan_tasks(
    research_id: uuid.UUID,
    service: ResearchPlanService = Depends(_service),
) -> list[PlanTaskOut]:
    try:
        tasks = service.list_tasks(research_id)
    except ResearchPlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [PlanTaskOut.model_validate(task) for task in tasks]
