"""DTOs for PDF extraction (RDA-020).

``document_id`` mirrors ``app.models.document.Document.id``, which is a
UUID (see RDA-017), not the plain ``int`` shown in the ticket's simplified
example.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExtractedPage(BaseModel):
    """Text extracted from a single PDF page."""

    model_config = ConfigDict(extra="forbid")

    page_number: int
    text: str
    char_count: int


class ExtractionResult(BaseModel):
    """The full text of a document, preserving page boundaries."""

    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID | None = None
    pages: list[ExtractedPage]
    total_pages: int
    total_chars: int
    extracted_at: datetime
