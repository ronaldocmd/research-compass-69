"""OpenAlex adapter for the SearchProvider contract (RDA-012).

Talks to https://api.openalex.org/works and converts each raw work into a
NormalizedSearchResult, so the rest of the system never sees OpenAlex's
native response shape.
"""

from typing import Any

import httpx

from app.core.config import settings
from app.schemas.search import NormalizedSearchResult, SearchOptions
from app.services.search.exceptions import (
    SearchProviderError,
    SearchProviderHTTPError,
    SearchProviderInvalidResponseError,
    SearchProviderRateLimitError,
    SearchProviderTimeoutError,
)
from app.services.search.provider import SearchProvider


class OpenAlexSearchProvider(SearchProvider):
    """SearchProvider adapter backed by the OpenAlex Works API."""

    name = "openalex"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        email: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = (base_url if base_url is not None else settings.OPENALEX_BASE_URL).rstrip("/")
        self._email = email if email is not None else settings.OPENALEX_EMAIL
        self._timeout = timeout if timeout is not None else settings.OPENALEX_TIMEOUT_SECONDS
        self._client = client

    def search(
        self,
        query: str,
        options: SearchOptions | None = None,
    ) -> list[NormalizedSearchResult]:
        options = options or SearchOptions()
        params: dict[str, Any] = {
            "search": query,
            "per-page": options.limit,
            "page": (options.offset // options.limit) + 1,
        }
        if self._email:
            params["mailto"] = self._email
        params.update(options.filters)

        response = self._request(params)
        payload = self._parse_json(response)

        results = payload.get("results")
        if not isinstance(results, list):
            raise SearchProviderInvalidResponseError(
                "OpenAlex response is missing a 'results' list"
            )
        return [self._normalize(item) for item in results if isinstance(item, dict)]

    def _request(self, params: dict[str, Any]) -> httpx.Response:
        url = f"{self._base_url}/works"
        try:
            if self._client is not None:
                response = self._client.get(url, params=params, timeout=self._timeout)
            else:
                response = httpx.get(url, params=params, timeout=self._timeout)
        except httpx.TimeoutException as exc:
            raise SearchProviderTimeoutError("OpenAlex request timed out") from exc
        except httpx.HTTPError as exc:
            raise SearchProviderError(f"OpenAlex request failed: {exc}") from exc

        if response.status_code == 429:
            raise SearchProviderRateLimitError("OpenAlex rate limit exceeded (HTTP 429)")
        if response.status_code >= 400:
            raise SearchProviderHTTPError(
                response.status_code,
                f"OpenAlex returned HTTP {response.status_code}",
            )
        return response

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise SearchProviderInvalidResponseError("OpenAlex returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise SearchProviderInvalidResponseError("OpenAlex returned an unexpected payload shape")
        return payload

    def _normalize(self, item: dict[str, Any]) -> NormalizedSearchResult:
        doi_url = item.get("doi")
        doi = doi_url.removeprefix("https://doi.org/") if isinstance(doi_url, str) else None
        openalex_id = item.get("id")

        primary_location = item.get("primary_location") or {}
        landing_page_url = (
            primary_location.get("landing_page_url") if isinstance(primary_location, dict) else None
        )
        url = doi_url or landing_page_url or openalex_id

        authors = self._extract_authors(item.get("authorships"))
        abstract = self._reconstruct_abstract(item.get("abstract_inverted_index"))

        metadata: dict[str, Any] = {}
        if item.get("type") is not None:
            metadata["type"] = item.get("type")
        if item.get("cited_by_count") is not None:
            metadata["cited_by_count"] = item.get("cited_by_count")

        return NormalizedSearchResult(
            source=self.name,
            title=item.get("title") or item.get("display_name"),
            authors=authors,
            abstract=abstract,
            publication_year=item.get("publication_year"),
            doi=doi,
            url=url,
            external_id=openalex_id,
            metadata=metadata,
        )

    @staticmethod
    def _extract_authors(authorships: Any) -> list[str]:
        if not isinstance(authorships, list):
            return []
        authors: list[str] = []
        for authorship in authorships:
            if not isinstance(authorship, dict):
                continue
            author = authorship.get("author")
            name = author.get("display_name") if isinstance(author, dict) else None
            if name:
                authors.append(name)
        return authors

    @staticmethod
    def _reconstruct_abstract(inverted_index: Any) -> str | None:
        if not isinstance(inverted_index, dict) or not inverted_index:
            return None
        positions: dict[int, str] = {}
        for word, indexes in inverted_index.items():
            if not isinstance(indexes, list):
                continue
            for index in indexes:
                if isinstance(index, int):
                    positions[index] = word
        if not positions:
            return None
        return " ".join(positions[index] for index in sorted(positions))
