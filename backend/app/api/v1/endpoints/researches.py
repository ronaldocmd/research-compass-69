"""REST endpoints for Research (RDA-006): /api/v1/researches."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.research import ResearchCreate, ResearchResponse, ResearchUpdate
from app.services.research_service import ResearchNotFoundError, ResearchService

router = APIRouter()


def _service(db: Session = Depends(get_db)) -> ResearchService:
    return ResearchService(db)


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
