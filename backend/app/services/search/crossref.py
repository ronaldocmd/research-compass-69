"""Crossref adapter for the SearchProvider contract (RDA-013).

Talks to https://api.crossref.org/works and converts each raw work into a
NormalizedSearchResult, so the rest of the system never sees Crossref's
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


class CrossrefSearchProvider(SearchProvider):
    """SearchProvider adapter backed by the Crossref Works API."""

    name = "crossref"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        email: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = (base_url if base_url is not None else settings.CROSSREF_BASE_URL).rstrip("/")
        self._email = email if email is not None else settings.CROSSREF_EMAIL
        self._timeout = timeout if timeout is not None else settings.CROSSREF_TIMEOUT_SECONDS
        self._client = client

    def search(
        self,
        query: str,
        options: SearchOptions | None = None,
    ) -> list[NormalizedSearchResult]:
        options = options or SearchOptions()
        params: dict[str, Any] = {
            "query": query,
            "rows": options.limit,
            "offset": options.offset,
        }
        if self._email:
            params["mailto"] = self._email
        params.update(options.filters)

        response = self._request(params)
        payload = self._parse_json(response)

        message = payload.get("message")
        if not isinstance(message, dict):
            raise SearchProviderInvalidResponseError(
                "Crossref response is missing a 'message' object"
            )
        items = message.get("items")
        if not isinstance(items, list):
            raise SearchProviderInvalidResponseError(
                "Crossref response is missing a 'message.items' list"
            )
        return [self._normalize(item) for item in items if isinstance(item, dict)]

    def _request(self, params: dict[str, Any]) -> httpx.Response:
        url = f"{self._base_url}/works"
        try:
            if self._client is not None:
                response = self._client.get(url, params=params, timeout=self._timeout)
            else:
                response = httpx.get(url, params=params, timeout=self._timeout)
        except httpx.TimeoutException as exc:
            raise SearchProviderTimeoutError("Crossref request timed out") from exc
        except httpx.HTTPError as exc:
            raise SearchProviderError(f"Crossref request failed: {exc}") from exc

        if response.status_code == 429:
            raise SearchProviderRateLimitError("Crossref rate limit exceeded (HTTP 429)")
        if response.status_code >= 400:
            raise SearchProviderHTTPError(
                response.status_code,
                f"Crossref returned HTTP {response.status_code}",
            )
        return response

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise SearchProviderInvalidResponseError("Crossref returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise SearchProviderInvalidResponseError("Crossref returned an unexpected payload shape")
        return payload

    def _normalize(self, item: dict[str, Any]) -> NormalizedSearchResult:
        doi = item.get("DOI")
        title = self._first_or_none(item.get("title"))

        url = self._extract_url(item, doi)
        authors = self._extract_authors(item.get("author"))
        publication_year = self._extract_year(item.get("published")) or self._extract_year(
            item.get("created")
        )
        abstract = item.get("abstract") if isinstance(item.get("abstract"), str) else None

        metadata: dict[str, Any] = {}
        if item.get("type") is not None:
            metadata["type"] = item.get("type")
        if item.get("is-referenced-by-count") is not None:
            metadata["is_referenced_by_count"] = item.get("is-referenced-by-count")

        return NormalizedSearchResult(
            source=self.name,
            title=title,
            authors=authors,
            abstract=abstract,
            publication_year=publication_year,
            doi=doi,
            url=url,
            external_id=doi,
            metadata=metadata,
        )

    @staticmethod
    def _first_or_none(value: Any) -> str | None:
        if isinstance(value, list) and value and isinstance(value[0], str):
            return value[0]
        return None

    @staticmethod
    def _extract_url(item: dict[str, Any], doi: Any) -> str | None:
        resource = item.get("resource")
        if isinstance(resource, dict):
            primary = resource.get("primary")
            if isinstance(primary, dict):
                primary_url = primary.get("URL")
                if isinstance(primary_url, str):
                    return primary_url

        link = item.get("link")
        if isinstance(link, list):
            for entry in link:
                if isinstance(entry, dict) and isinstance(entry.get("URL"), str):
                    return entry["URL"]

        if isinstance(doi, str):
            return f"https://doi.org/{doi}"
        return None

    @staticmethod
    def _extract_authors(author_field: Any) -> list[str]:
        if not isinstance(author_field, list):
            return []
        authors: list[str] = []
        for author in author_field:
            if not isinstance(author, dict):
                continue
            given = author.get("given")
            family = author.get("family")
            name = " ".join(part for part in (given, family) if isinstance(part, str) and part)
            if name:
                authors.append(name)
            elif isinstance(author.get("name"), str) and author.get("name"):
                authors.append(author["name"])
        return authors

    @staticmethod
    def _extract_year(date_field: Any) -> int | None:
        if not isinstance(date_field, dict):
            return None
        date_parts = date_field.get("date-parts")
        if not isinstance(date_parts, list) or not date_parts:
            return None
        first_part = date_parts[0]
        if not isinstance(first_part, list) or not first_part:
            return None
        year = first_part[0]
        return year if isinstance(year, int) else None
