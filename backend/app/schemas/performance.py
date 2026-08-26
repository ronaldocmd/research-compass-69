"""Pydantic schemas for performance reporting (RDA-051)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResearchPerformanceResponse(BaseModel):
    """Timing report for one research run."""

    model_config = ConfigDict(extra="forbid")

    research_id: uuid.UUID
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None = Field(ge=0)
