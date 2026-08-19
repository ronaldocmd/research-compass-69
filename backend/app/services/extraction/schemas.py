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


class DocumentElement(BaseModel):
    """A structural element detected on a page (RDA-021).

    ``type`` is one of "heading", "paragraph" or "table". ``level`` is only
    meaningful for headings (1 for the largest detected font, 2 for the
    next, and so on).
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    level: int | None = None
    text: str
    page_number: int
    position: int


class StructuredPage(BaseModel):
    """A page broken down into its structural elements."""

    model_config = ConfigDict(extra="forbid")

    page_number: int
    elements: list[DocumentElement]


class StructuredExtractionResult(BaseModel):
    """The full document, preserving headings, paragraphs and tables.

    ``document_id`` is a UUID for the same reason as in ExtractionResult.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID | None = None
    pages: list[StructuredPage]
    total_pages: int
    extracted_at: datetime
