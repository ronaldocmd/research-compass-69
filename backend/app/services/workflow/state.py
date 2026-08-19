"""Typed, serializable research workflow state (RDA-032).

Holds the full snapshot of one research execution. Consumed by the
orchestrator (RDA-033) to control the flow, and serializable to JSON for
checkpointing (jsonb/text compatible). UUID fields use ``uuid.UUID`` to stay
consistent with the rest of the codebase (Pydantic serializes them to JSON
strings, so the round-trip is lossless).
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.search import NormalizedSearchResult
from app.services.claims.schemas import Claim
from app.services.evidence.schemas import Evidence
from app.services.planning.schemas import PlanTask


class WorkflowStage(str, Enum):
    """The stages a research execution moves through."""

    IDLE = "IDLE"
    PLANNING = "PLANNING"
    SEARCHING = "SEARCHING"
    SELECTING = "SELECTING"
    PROCESSING = "PROCESSING"
    EXTRACTING = "EXTRACTING"
    SYNTHESIZING = "SYNTHESIZING"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


class BudgetState(BaseModel):
    """Usage counters and limits for one execution."""

    model_config = ConfigDict(extra="forbid")

    llm_calls: int = 0
    total_tokens: int = 0
    search_calls: int = 0
    processing_operations: int = 0
    estimated_cost_usd: float = 0.0
    max_llm_calls: int = 50
    max_search_calls: int = 20
    max_cost_usd: float = 5.0
    is_exceeded: bool = False


class ErrorSeverity(str, Enum):
    """How an error should be treated by the orchestrator."""

    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"
    VALIDATION = "VALIDATION"
    PROVIDER = "PROVIDER"
    PROCESSING = "PROCESSING"


class WorkflowError(BaseModel):
    """A recorded error within an execution."""

    model_config = ConfigDict(extra="forbid")

    error_id: uuid.UUID
    stage: WorkflowStage
    message: str
    severity: ErrorSeverity
    timestamp: datetime
    retryable: bool
    context: dict[str, Any] = Field(default_factory=dict)


class ResearchWorkflowState(BaseModel):
    """The complete, serializable state of one research execution."""

    model_config = ConfigDict(extra="forbid")

    # Identification
    research_id: uuid.UUID
    execution_id: uuid.UUID
    current_stage: WorkflowStage = WorkflowStage.IDLE

    # Plan
    plan_id: uuid.UUID | None = None
    tasks: list[PlanTask] = Field(default_factory=list)

    # Search
    search_queries: list[str] = Field(default_factory=list)
    search_results: list[NormalizedSearchResult] = Field(default_factory=list)
    selected_documents: list[uuid.UUID] = Field(default_factory=list)

    # Processing
    processed_document_ids: list[uuid.UUID] = Field(default_factory=list)
    failed_document_ids: list[uuid.UUID] = Field(default_factory=list)
    processing_status: dict[uuid.UUID, str] = Field(default_factory=dict)

    # Evidence engine
    chunk_ids: list[uuid.UUID] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    evidence_items: list[Evidence] = Field(default_factory=list)

    # Errors
    errors: list[WorkflowError] = Field(default_factory=list)
    retry_count: int = 0

    # Budget
    budget: BudgetState = Field(default_factory=BudgetState)

    # Metadata
    started_at: datetime | None = None
    updated_at: datetime
    completed_at: datetime | None = None
    checkpointed_at: datetime | None = None
