"""Provider-agnostic search DTOs (RDA-011 / RDA-015).

These structures are the normalized contract shared by every SearchProvider
implementation (OpenAlex, Crossref, ...), so the Search Service never
depends on a specific provider's response shape.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Imported lazily inside the validator below (not at module load time):
# app.services.search.provider/openalex/crossref all import from this very
# module, so importing app.services.search eagerly here would create a
# circular import. By the time a NormalizedSearchResult is instantiated,
# that package is safe to import.


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

    @model_validator(mode="after")
    def _normalize(self) -> "NormalizedSearchResult":
        """Apply provider-agnostic normalization/validation (RDA-015).

        Runs for every NormalizedSearchResult regardless of which provider
        built it, so OpenAlex/Crossref/future providers never need to
        duplicate this logic themselves. Invalid publication_year/doi/url
        values are reset to None but preserved under metadata["raw_*"] so
        no information from the source is silently lost.
        """
        from app.services.search.normalizer import (
            normalize_abstract,
            normalize_authors,
            normalize_doi,
            normalize_title,
            normalize_url,
            normalize_year,
        )

        self.title = normalize_title(self.title)
        self.authors = normalize_authors(self.authors)
        self.abstract = normalize_abstract(self.abstract)

        normalized_year = normalize_year(self.publication_year)
        if self.publication_year is not None and normalized_year is None:
            self.metadata.setdefault("raw_publication_year", self.publication_year)
        self.publication_year = normalized_year

        normalized_doi = normalize_doi(self.doi)
        if self.doi is not None and normalized_doi is None:
            self.metadata.setdefault("raw_doi", self.doi)
        self.doi = normalized_doi

        normalized_url = normalize_url(self.url)
        if self.url is not None and normalized_url is None:
            self.metadata.setdefault("raw_url", self.url)
        self.url = normalized_url

        return self
