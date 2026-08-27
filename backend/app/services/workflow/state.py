"""Typed, serializable research workflow state (RDA-032).

Holds the full snapshot of one research execution. Consumed by the
orchestrator (RDA-033) to control the flow, and serializable to JSON for
checkpointing (jsonb/text compatible). UUID fields use ``uuid.UUID`` to stay
consistent with the rest of the codebase (Pydantic serializes them to JSON
strings, so the round-trip is lossless).
"""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.search import NormalizedSearchResult
from app.services.claims.schemas import Claim
from app.services.confidence.schemas import ScoredClaim
from app.services.evidence.schemas import Evidence
from app.services.planning.schemas import PlanTask
from app.services.provenance.schemas import ProvenanceChain
from app.services.retrieval.schemas import RetrievedChunk
from app.services.validation.schemas import ValidationResult


class WorkflowStage(str, Enum):
    """The stages a research execution moves through."""

    IDLE = "IDLE"
    START = "IDLE"
    PLANNING = "PLANNING"
    SEARCH = "SEARCH"
    SEARCHING = "SEARCH"
    SELECTING = "SELECTING"
    PROCESSING = "PROCESSING"
    EXTRACTING = "EXTRACTING"
    VALIDATING = "VALIDATING"
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
    max_processing_operations: int = 100
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

    # Research intent (RDA-058). Captured at planning time so downstream
    # nodes (selection, evidence) can condition on the actual research
    # question instead of generic task titles.
    research_question: str | None = None
    research_objective: str | None = None

    # Search
    search_queries: list[str] = Field(default_factory=list)
    search_results: list[NormalizedSearchResult | dict[str, Any]] = Field(default_factory=list)
    selected_documents: list[uuid.UUID] = Field(default_factory=list)
    selected_ids: list[str] = Field(default_factory=list)

    # Selection observability (RDA-058). Counts of where search results are
    # dropped so the pipeline can be diagnosed end-to-end.
    selection_stats: dict[str, int] = Field(default_factory=dict)

    # Processing
    processed_document_ids: list[uuid.UUID] = Field(default_factory=list)
    failed_document_ids: list[uuid.UUID] = Field(default_factory=list)
    processing_status: dict[uuid.UUID, str] = Field(default_factory=dict)

    # Evidence engine
    chunk_ids: list[uuid.UUID] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    evidence_items: list[Evidence] = Field(default_factory=list)

    # Epistemological chain (RDA-061). The evidence node records the chunks
    # it retrieved so the validation node can rebuild RetrievedChunk and
    # DocumentSource for provenance; validation/provenance/confidence are
    # produced by the validation node and consumed by synthesis.
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    validation_results: list[ValidationResult] = Field(default_factory=list)
    provenance_chains: list[ProvenanceChain] = Field(default_factory=list)
    scored_claims: list[ScoredClaim] = Field(default_factory=list)
    # Observability of the synthesis filter (RDA-061): how many claims were
    # considered and how many were excluded for low confidence.
    synthesis_stats: dict[str, int] = Field(default_factory=dict)

    # Errors
    errors: list[WorkflowError] = Field(default_factory=list)
    retry_count: int = 0

    # Budget
    budget: BudgetState = Field(default_factory=BudgetState)

    # Metadata
    started_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    checkpointed_at: datetime | None = None
