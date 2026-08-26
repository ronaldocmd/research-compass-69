"""REST endpoints for human evaluation (RDA-049)."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.evaluation_repository import EvaluationRepository
from app.schemas.evaluation import (
    EvaluationStats,
    HumanEvaluationCreate,
    HumanEvaluationResponse,
)

router = APIRouter()


def _repo(db: Session = Depends(get_db)) -> EvaluationRepository:
    return EvaluationRepository(db)


@router.post(
    "/evaluations",
    response_model=HumanEvaluationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_evaluation(
    payload: HumanEvaluationCreate,
    repo: EvaluationRepository = Depends(_repo),
) -> HumanEvaluationResponse:
    return HumanEvaluationResponse.model_validate(repo.create_evaluation(payload))


@router.get("/evaluations", response_model=list[HumanEvaluationResponse])
def list_evaluations(
    claim_id: uuid.UUID | None = Query(default=None),
    repo: EvaluationRepository = Depends(_repo),
) -> list[HumanEvaluationResponse]:
    if claim_id is not None:
        return [
            HumanEvaluationResponse.model_validate(item)
            for item in repo.get_by_claim(claim_id)
        ]
    return []


@router.get(
    "/researches/{research_id}/evaluations",
    response_model=list[HumanEvaluationResponse],
)
def get_evaluations(
    research_id: uuid.UUID,
    repo: EvaluationRepository = Depends(_repo),
) -> list[HumanEvaluationResponse]:
    return [
        HumanEvaluationResponse.model_validate(item)
        for item in repo.get_by_research(research_id)
    ]


@router.get(
    "/researches/{research_id}/evaluation-stats",
    response_model=EvaluationStats,
)
def get_evaluation_stats(
    research_id: uuid.UUID,
    repo: EvaluationRepository = Depends(_repo),
) -> EvaluationStats:
    return EvaluationStats.model_validate(repo.get_statistics(research_id))
