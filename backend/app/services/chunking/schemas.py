"""DTOs for document chunking (RDA-022).

``document_id`` mirrors ``app.models.document.Document.id``, which is a
UUID (see RDA-017), not the plain ``int`` shown in the ticket's simplified
example — the same deviation already documented in
``app.services.extraction.schemas``.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Chunk(BaseModel):
    """A retrieval-sized slice of a document's structured text."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: uuid.UUID
    document_id: uuid.UUID | None = None
    text: str
    page_number: int
    section: str | None = None
    index: int
    char_count: int


class ChunkingResult(BaseModel):
    """All chunks produced for a document."""

    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID | None = None
    chunks: list[Chunk]
    total_chunks: int
    strategy: str
    chunked_at: datetime
