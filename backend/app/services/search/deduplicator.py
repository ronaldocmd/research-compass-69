"""Deduplication of NormalizedSearchResult across providers (RDA-016).

Multiple providers (or repeated pages of the same provider) can return the
same underlying document. SearchDeduplicator collapses those duplicates
into a single, metadata-merged NormalizedSearchResult, using this
hierarchy of identity signals, evaluated per result against every other
still-standalone result:

    1. DOI (most reliable, when non-None on both sides)
    2. external_id (provider-native identifier, when non-None on both sides)
    3. Normalized URL (protocol/trailing-slash/query-string differences ignored)
    4. Content hash: normalized title + first author + publication year

A content hash is intentionally the last resort and requires an exact
match on all three components: near-duplicate titles like "Machine
Learning in Medicine" vs "Machine Learning in Medical Imaging" are NOT
considered duplicates, since fuzzy title matching risks discarding
genuinely different documents.
"""

import hashlib
import re
from urllib.parse import urlparse

from app.schemas.search import NormalizedSearchResult

DEFAULT_PROVIDER_PREFERENCE = ["openalex", "crossref"]


class SearchDeduplicator:
    """Collapses duplicate NormalizedSearchResult entries from one or more providers."""

    def __init__(self, provider_preference: list[str] | None = None) -> None:
        self._provider_preference = provider_preference or DEFAULT_PROVIDER_PREFERENCE

    def deduplicate(
        self,
        results: list[NormalizedSearchResult],
        strategy: str = "hierarchical",
    ) -> list[NormalizedSearchResult]:
        """Remove duplicates from ``results``, merging complementary data.

        Args:
            results: Normalized results, possibly from multiple providers.
            strategy: Deduplication strategy. Only "hierarchical" (DOI ->
                external_id -> normalized URL -> content hash) is
                implemented; any other value raises ValueError.

        Returns:
            A new list with duplicates merged into a single entry each,
            ordered by first occurrence, most-preferred provider first
            among genuine duplicates.
        """
        if strategy != "hierarchical":
            raise ValueError(f"Unknown deduplication strategy: {strategy!r}")

        if not results:
            return []

        ordered = self._order_by_provider_preference(results)

        merged: list[NormalizedSearchResult] = []
        for candidate in ordered:
            match_index = self._find_duplicate_index(candidate, merged)
            if match_index is None:
                merged.append(candidate)
            else:
                merged[match_index] = self._merge_results(merged[match_index], candidate)

        return merged

    def _order_by_provider_preference(
        self, results: list[NormalizedSearchResult]
    ) -> list[NormalizedSearchResult]:
        def rank(result: NormalizedSearchResult) -> int:
            try:
                return self._provider_preference.index(result.source)
            except ValueError:
                return len(self._provider_preference)

        return sorted(results, key=rank)

    def _find_duplicate_index(
        self,
        candidate: NormalizedSearchResult,
        existing: list[NormalizedSearchResult],
    ) -> int | None:
        for index, other in enumerate(existing):
            if self._are_duplicates(candidate, other):
                return index
        return None

    def _are_duplicates(
        self, a: NormalizedSearchResult, b: NormalizedSearchResult
    ) -> bool:
        if a.doi is not None and b.doi is not None and a.doi == b.doi:
            return True
        if (
            a.external_id is not None
            and b.external_id is not None
            and a.external_id == b.external_id
        ):
            return True

        url_a, url_b = self._normalize_url(a.url), self._normalize_url(b.url)
        if url_a is not None and url_b is not None and url_a == url_b:
            return True

        hash_a, hash_b = self._content_hash(a), self._content_hash(b)
        if hash_a is not None and hash_b is not None and hash_a == hash_b:
            return True

        return False

    @staticmethod
    def _normalize_url(url: str | None) -> str | None:
        """Strip protocol, trailing slash and query/fragment for comparison."""
        if not url:
            return None
        parsed = urlparse(url)
        if not parsed.netloc:
            return None
        path = parsed.path.rstrip("/")
        return f"{parsed.netloc.lower()}{path}".lower() or None

    @staticmethod
    def _content_hash(result: NormalizedSearchResult) -> str | None:
        """Hash of normalized title + first author + year; None if title/year missing."""
        if not result.title or result.publication_year is None:
            return None

        normalized_title = re.sub(r"\s+", " ", result.title.strip().lower())
        first_author = result.authors[0].strip().lower() if result.authors else ""
        raw = f"{normalized_title}|{first_author}|{result.publication_year}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _merge_results(
        primary: NormalizedSearchResult, secondary: NormalizedSearchResult
    ) -> NormalizedSearchResult:
        """Merge ``secondary`` into ``primary``, preferring primary's non-None fields.

        ``primary`` is the higher-preference (or first-seen) result. Fields
        missing on primary are filled in from secondary; metadata from both
        is merged (primary wins on key conflicts), and each source's
        metadata is recorded so no provider-specific detail is lost.
        """
        merged_metadata = {**secondary.metadata, **primary.metadata}
        merged_metadata.setdefault("merged_sources", [])
        for source in (secondary.source, primary.source):
            if source not in merged_metadata["merged_sources"]:
                merged_metadata["merged_sources"].append(source)

        return NormalizedSearchResult(
            source=primary.source,
            title=primary.title or secondary.title,
            authors=primary.authors or secondary.authors,
            abstract=primary.abstract or secondary.abstract,
            publication_year=primary.publication_year
            if primary.publication_year is not None
            else secondary.publication_year,
            doi=primary.doi or secondary.doi,
            url=primary.url or secondary.url,
            external_id=primary.external_id or secondary.external_id,
            metadata=merged_metadata,
        )
