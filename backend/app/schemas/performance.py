"""Pydantic schemas for performance reporting (RDA-051)."""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class StageMetric(BaseModel):
    """Duration and outcome of a single workflow stage."""

    model_config = ConfigDict(extra="forbid")

    stage: str
    duration_seconds: float = Field(ge=0)
    status: str  # "success" | "failed"


class PerformanceReport(BaseModel):
    """Aggregated performance metrics for one research run."""

    model_config = ConfigDict(extra="forbid")

    research_id: uuid.UUID
    time_to_first_result: float | None = Field(ge=0)
    time_to_completion: float = Field(ge=0)
    documents_found: int = Field(ge=0)
    documents_processed: int = Field(ge=0)
    throughput_docs_per_minute: float = Field(ge=0)
    error_rate: float = Field(ge=0, le=1)
    stages: list[StageMetric]
