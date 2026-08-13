from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Database-aware health payload returned by GET /api/v1/health."""

    status: Literal["ok", "degraded"] = Field(description="Overall API status")
    database: Literal["up", "down"] = Field(description="PostgreSQL connectivity")
    version: str
    environment: str
