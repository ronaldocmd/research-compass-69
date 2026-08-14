"""Pydantic request/response schemas for the Research API (RDA-006)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.research import ResearchStatus


class ResearchCreate(BaseModel):
    """Payload accepted by POST /api/v1/researches."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1)
    question: str = Field(min_length=1)
    status: ResearchStatus = ResearchStatus.DRAFT


class ResearchUpdate(BaseModel):
    """Partial payload accepted by PATCH /api/v1/researches/{id}."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=200)
    objective: str | None = Field(default=None, min_length=1)
    question: str | None = Field(default=None, min_length=1)
    status: ResearchStatus | None = None


class ResearchResponse(BaseModel):
    """Research as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    objective: str
    question: str
    status: ResearchStatus
    created_at: datetime
    updated_at: datetime
