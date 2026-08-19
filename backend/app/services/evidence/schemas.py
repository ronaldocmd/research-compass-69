"""DTOs for evidence extraction (RDA-026).

``chunk_id``/``document_id`` mirror the ORM models (app.models.chunk /
app.models.document), which use UUIDs — the same convention as the rest of
the codebase (see app.services.retrieval.schemas).
"""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class EvidenceStatus(str, Enum):
    """How strongly the available chunks support a claim."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    INCONCLUSIVE = "inconclusive"


class EvidenceDraft(BaseModel):
    """What the LLM returns: an extracted passage plus its status.

    ``text`` and ``chunk_id`` are None when there is no supporting passage
    (e.g. ``unsupported``).
    """

    model_config = ConfigDict(extra="forbid")

    text: str | None = None
    chunk_id: uuid.UUID | None = None
    status: EvidenceStatus


class Evidence(BaseModel):
    """A validated piece of evidence tied back to its source chunk.

    ``text`` is only populated when the passage was actually grounded in the
    source chunk (never invented). ``document_id``/``page_number`` are
    inherited from that chunk.
    """

    model_config = ConfigDict(extra="forbid")

    evidence_id: uuid.UUID
    claim_id: uuid.UUID
    text: str | None = None
    chunk_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    page_number: int | None = None
    status: EvidenceStatus
    extracted_at: datetime


class EvidenceExtractionResult(BaseModel):
    """All evidence found for a single claim, plus the aggregated status."""

    model_config = ConfigDict(extra="forbid")

    claim_id: uuid.UUID
    evidence: list[Evidence]
    final_status: EvidenceStatus
    extracted_at: datetime


class EvidenceExtractionResponse(BaseModel):
    """Structured-output contract handed to the LLMProvider (RDA-026)."""

    model_config = ConfigDict(extra="forbid")

    evidence: list[EvidenceDraft]
