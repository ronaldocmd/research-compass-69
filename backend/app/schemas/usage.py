"""Pydantic schemas for cost/usage reporting (RDA-050)."""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class ResearchCostResponse(BaseModel):
    """Aggregated cost report for one research."""

    model_config = ConfigDict(extra="forbid")

    research_id: uuid.UUID
    llm_calls: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    search_calls: int = Field(ge=0)
    processing_operations: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
