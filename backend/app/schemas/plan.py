"""Pydantic request/response schemas for the plan API (RDA-031)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.plan import PlanStatus, TaskStatus, TaskType


class PlanRequest(BaseModel):
    """Payload accepted by POST /researches/{research_id}/plan."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    language: str = "en"
    depth: Literal["basic", "standard", "deep"] = "standard"
    sources: list[str] = Field(default_factory=list)


class PlanTaskOut(BaseModel):
    """A persisted plan task as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    priority: int
    task_type: TaskType
    status: TaskStatus
    order: int
    result_summary: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class PlanOut(BaseModel):
    """A persisted plan (with its tasks) as returned by the API."""

    id: uuid.UUID
    research_id: uuid.UUID
    status: PlanStatus
    created_at: datetime
    updated_at: datetime
    tasks: list[PlanTaskOut] = Field(default_factory=list)
