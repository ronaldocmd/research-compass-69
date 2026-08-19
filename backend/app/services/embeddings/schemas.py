"""DTOs for embedding generation (RDA-023).

``chunk_id`` mirrors ``app.services.chunking.schemas.Chunk.chunk_id``
(a UUID), for the same reason document_id is a UUID elsewhere in this
codebase (see app.services.extraction.schemas).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EmbeddingResult(BaseModel):
    """The outcome of embedding a single chunk: success or failure.

    On success, ``embedding``/``model``/``dimension``/``embedded_at`` are
    populated and ``error`` is None. On failure, ``embedding`` is None and
    ``error`` carries a human-readable reason so the caller can retry or
    report without losing track of which chunk failed.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: uuid.UUID
    embedding: list[float] | None = None
    model: str | None = None
    dimension: int | None = None
    embedded_at: datetime | None = None
    success: bool = True
    error: str | None = None
