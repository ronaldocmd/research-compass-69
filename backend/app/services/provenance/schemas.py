"""DTOs for provenance (RDA-029)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProvenanceLink(BaseModel):
    """One step in the provenance chain.

    ``level`` is one of "claim", "evidence", "chunk", "page", "document" or
    "source". ``id`` is the identifier of the object at that level (kept as a
    string for flexibility).
    """

    model_config = ConfigDict(extra="forbid")

    level: str
    id: str
    description: str


class ProvenanceChain(BaseModel):
    """The full origin chain of a claim, ordered from claim to source."""

    model_config = ConfigDict(extra="forbid")

    claim_id: uuid.UUID
    chain: list[ProvenanceLink]
    resolved_at: datetime
    is_complete: bool


class DocumentSource(BaseModel):
    """Original-source metadata for a document (URL/DOI/title)."""

    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID
    title: str | None = None
    url: str | None = None
    doi: str | None = None
    page_number: int | None = None
    chunk_id: uuid.UUID
