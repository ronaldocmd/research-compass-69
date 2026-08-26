"""Pydantic request/response schemas for human evaluation (RDA-049)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Rating = Literal["correct", "incorrect", "inconclusive"]


class HumanEvaluationCreate(BaseModel):
    """Payload accepted by POST /api/v1/evaluations.

    ``research_id`` is stored so evaluations can be queried and aggregated per
    research (claims are not persisted in their own table yet).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    claim_id: uuid.UUID
    research_id: uuid.UUID
    evaluator_id: str = Field(min_length=1, max_length=255)
    rating: Rating
    comment: str | None = Field(default=None, max_length=5000)


class HumanEvaluationResponse(BaseModel):
    """Human evaluation as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_id: uuid.UUID
    research_id: uuid.UUID
    evaluator_id: str
    rating: str
    comment: str | None
    evaluated_at: datetime


class EvaluationStats(BaseModel):
    """Simple rating distribution for one research (percentages 0..1)."""

    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0)
    correct: float = Field(ge=0, le=1)
    incorrect: float = Field(ge=0, le=1)
    inconclusive: float = Field(ge=0, le=1)
