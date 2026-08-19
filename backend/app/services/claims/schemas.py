"""DTOs for claim extraction (RDA-025).

``chunk_id``/``document_id`` mirror the ORM models (app.models.chunk /
app.models.document), which use UUIDs — the same convention as the rest of
the codebase (see app.services.retrieval.schemas).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Claim(BaseModel):
    """A single verifiable factual claim extracted from source chunks.

    ``chunk_ids`` is never empty: the extractor discards claims without a
    valid source reference. ``document_id`` and ``page_number`` are derived
    from the first referenced source chunk, never trusted from the LLM.
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: uuid.UUID
    text: str
    chunk_ids: list[uuid.UUID]
    document_id: uuid.UUID
    page_number: int | None = None
    extracted_at: datetime


class ClaimExtractionResult(BaseModel):
    """All valid claims extracted for a query."""

    model_config = ConfigDict(extra="forbid")

    query: str
    claims: list[Claim]
    total_claims: int
    model_used: str
    extracted_at: datetime


class ClaimDraft(BaseModel):
    """The shape of one claim the LLM is asked to produce.

    ``chunk_ids`` is optional here (a claim with no chunk_ids is discarded
    silently by ClaimExtractor rather than failing the whole response).
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    chunk_ids: list[uuid.UUID] = Field(default_factory=list)


class ClaimExtractionResponse(BaseModel):
    """Structured-output contract handed to the LLMProvider (RDA-025)."""

    model_config = ConfigDict(extra="forbid")

    claims: list[ClaimDraft]
