"""REST endpoints for Research (RDA-006): /api/v1/researches."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.performance import PerformanceReport
from app.schemas.research import ResearchCreate, ResearchResponse, ResearchUpdate
from app.schemas.usage import ResearchCostResponse
from app.services.performance.tracker import PerformanceTracker
from app.services.research_service import ResearchNotFoundError, ResearchService
from app.services.usage.tracker import UsageTracker

router = APIRouter()


def _service(db: Session = Depends(get_db)) -> ResearchService:
    return ResearchService(db)


def _usage_tracker(db: Session = Depends(get_db)) -> UsageTracker:
    return UsageTracker(db)


def _performance_tracker(db: Session = Depends(get_db)) -> PerformanceTracker:
    return PerformanceTracker(db)


def _not_found(exc: ResearchNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("", response_model=ResearchResponse, status_code=status.HTTP_201_CREATED)
def create_research(
    payload: ResearchCreate, service: ResearchService = Depends(_service)
) -> ResearchResponse:
    return ResearchResponse.model_validate(service.create(payload))


@router.get("", response_model=list[ResearchResponse])
def list_researches(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: ResearchService = Depends(_service),
) -> list[ResearchResponse]:
    return [ResearchResponse.model_validate(item) for item in service.list(limit=limit, offset=offset)]


@router.get("/{research_id}", response_model=ResearchResponse)
def get_research(
    research_id: uuid.UUID, service: ResearchService = Depends(_service)
) -> ResearchResponse:
    try:
        return ResearchResponse.model_validate(service.get(research_id))
    except ResearchNotFoundError as exc:
        raise _not_found(exc) from exc


@router.patch("/{research_id}", response_model=ResearchResponse)
def update_research(
    research_id: uuid.UUID,
    payload: ResearchUpdate,
    service: ResearchService = Depends(_service),
) -> ResearchResponse:
    try:
        return ResearchResponse.model_validate(service.update(research_id, payload))
    except ResearchNotFoundError as exc:
        raise _not_found(exc) from exc


@router.delete("/{research_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_research(
    research_id: uuid.UUID, service: ResearchService = Depends(_service)
) -> None:
    try:
        service.delete(research_id)
    except ResearchNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/{research_id}/cost", response_model=ResearchCostResponse)
def get_research_cost(
    research_id: uuid.UUID,
    service: ResearchService = Depends(_service),
    tracker: UsageTracker = Depends(_usage_tracker),
) -> ResearchCostResponse:
    """Return the estimated cost and usage breakdown for a research (RDA-050)."""
    try:
        service.get(research_id)
    except ResearchNotFoundError as exc:
        raise _not_found(exc) from exc
    return ResearchCostResponse.model_validate(tracker.get_report(research_id))


@router.get("/{research_id}/performance", response_model=PerformanceReport)
def get_research_performance(
    research_id: uuid.UUID,
    service: ResearchService = Depends(_service),
    tracker: PerformanceTracker = Depends(_performance_tracker),
) -> PerformanceReport:
    """Return the performance metrics for a research (RDA-051)."""
    try:
        service.get(research_id)
    except ResearchNotFoundError as exc:
        raise _not_found(exc) from exc
    return tracker.get_report(research_id)
