"""Provider-agnostic search DTOs (RDA-011).

These structures are the normalized contract shared by every SearchProvider
implementation (OpenAlex, Crossref, ...), so the Search Service never
depends on a specific provider's response shape.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SearchOptions(BaseModel):
    """Provider-agnostic search options accepted by SearchProvider.search()."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    filters: dict[str, Any] = Field(default_factory=dict)


class NormalizedSearchResult(BaseModel):
    """A single search result, normalized across all providers.

    Only ``source`` is required: every other field depends on what the
    upstream provider actually makes available for a given record.
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    publication_year: int | None = None
    doi: str | None = None
    url: str | None = None
    external_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
