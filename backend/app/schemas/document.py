"""Pydantic request/response schemas for Document (RDA-017)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus

KNOWN_SOURCES = {"openalex", "crossref"}


class DocumentBase(BaseModel):
    """Fields common to every Document representation.

    Used for payloads built directly (not read off the ORM model), so
    `metadata` here is a plain field: no aliasing needed.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source: str = Field(min_length=1, max_length=50)
    external_id: str | None = Field(default=None, max_length=500)
    title: str = Field(min_length=1, max_length=1000)
    authors: list[str] = Field(default_factory=list)
    publication_year: int | None = None
    doi: str | None = Field(default=None, max_length=255)
    url: str | None = Field(default=None, max_length=2000)
    abstract: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentCreate(DocumentBase):
    """Payload used to persist a Document for a given Research."""

    research_id: uuid.UUID
    status: DocumentStatus = DocumentStatus.PENDING
    relevance_score: float | None = None


class DocumentUpdate(BaseModel):
    """Partial payload for updating a Document."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=1000)
    authors: list[str] | None = None
    publication_year: int | None = None
    doi: str | None = Field(default=None, max_length=255)
    url: str | None = Field(default=None, max_length=2000)
    abstract: str | None = None
    metadata: dict[str, Any] | None = None
    status: DocumentStatus | None = None
    relevance_score: float | None = None


class _ORMDocumentBase(BaseModel):
    """Shared config/fields for DTOs built from the ORM Document instance.

    The `metadata` column is exposed on the ORM model as
    `document_metadata` (SQLAlchemy's declarative Base reserves the
    `metadata` name for the table MetaData object), so `validation_alias`
    bridges that gap when `from_attributes=True` reads the ORM object.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="document_metadata")


class DocumentInDB(_ORMDocumentBase):
    """Full Document representation as stored in the database."""

    id: uuid.UUID
    research_id: uuid.UUID
    source: str
    external_id: str | None
    title: str
    authors: list[str]
    publication_year: int | None
    doi: str | None
    url: str | None
    abstract: str | None
    status: DocumentStatus
    relevance_score: float | None = None
    created_at: datetime
    updated_at: datetime


class DocumentPublic(_ORMDocumentBase):
    """Document as returned by the API."""

    id: uuid.UUID
    research_id: uuid.UUID
    source: str
    external_id: str | None
    title: str
    authors: list[str]
    publication_year: int | None
    doi: str | None
    url: str | None
    abstract: str | None
    status: DocumentStatus
    relevance_score: float | None
    created_at: datetime
    updated_at: datetime
