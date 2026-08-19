"""DTOs for retrieval (RDA-024).

``chunk_id`` and ``document_id`` mirror the ORM models
(app.models.chunk.ChunkRecord.chunk_id / app.models.document.Document.id),
which are UUIDs — not the plain ``str``/``int`` shown in the ticket's
simplified example. This is the same deviation already documented in
app.services.chunking.schemas and app.services.extraction.schemas.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IndexedChunk(BaseModel):
    """A chunk plus its pre-computed embedding: one entry of the in-memory
    retrieval index (MVP without pgvector — RDA-024).

    Built from a ChunkRecord (app.models.chunk) and, when available, the
    owning Document's title.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    text: str
    page_number: int
    section: str | None = None
    embedding: list[float]
    document_title: str | None = None


class RetrievedChunk(BaseModel):
    """A chunk judged relevant for a query, with provenance and similarity."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    text: str
    page_number: int
    section: str | None = None
    score: float
    document_title: str | None = None


class RetrievalResult(BaseModel):
    """The outcome of a retrieval: the top-K chunks above ``min_score``.

    ``total_found`` counts every chunk whose similarity met ``min_score``,
    *before* ``top_k`` truncation, so it may be larger than ``len(chunks)``.
    """

    model_config = ConfigDict(extra="forbid")

    query: str
    chunks: list[RetrievedChunk]
    total_found: int
    retrieved_at: datetime
