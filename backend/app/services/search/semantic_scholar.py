"""Semantic Scholar adapter for the SearchProvider contract (RDA-066).

Uses the Graph API paper search. The API key is optional (it only raises the
rate limit); the planner's boolean syntax is reduced to keywords because the
endpoint does not understand AND/OR.
"""

import threading
import time
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.search import NormalizedSearchResult, SearchOptions
from app.services.search.common import get_response, parse_json_object, strip_boolean
from app.services.search.exceptions import SearchProviderInvalidResponseError
from app.services.search.provider import SearchProvider

_FIELDS = "title,abstract,year,authors,externalIds,openAccessPdf,url,citationCount"

# Process-wide throttle: SearchService builds new provider instances per run
# and several runs/queries can overlap, so the clock lives at module level
# (same rationale as arxiv.py). Semantic Scholar's 1 req/s limit is
# cumulative across every endpoint, not per provider instance.
_throttle_lock = threading.Lock()
_last_request_at = 0.0


def _wait_for_turn() -> None:
    """Block until ``SEMANTIC_SCHOLAR_MIN_INTERVAL_SECONDS`` passed since the last request."""
    global _last_request_at
    with _throttle_lock:
        wait = settings.SEMANTIC_SCHOLAR_MIN_INTERVAL_SECONDS - (
            time.monotonic() - _last_request_at
        )
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


class SemanticScholarSearchProvider(SearchProvider):
    """SearchProvider adapter backed by the Semantic Scholar Graph API."""

    name = "semantic_scholar"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = (base_url or settings.SEMANTIC_SCHOLAR_BASE_URL).rstrip("/")
        self._api_key = api_key if api_key is not None else settings.SEMANTIC_SCHOLAR_API_KEY
        self._timeout = timeout if timeout is not None else settings.SEMANTIC_SCHOLAR_TIMEOUT_SECONDS
        self._client = client

    def search(
        self, query: str, options: SearchOptions | None = None
    ) -> list[NormalizedSearchResult]:
        options = options or SearchOptions()
        params: dict[str, Any] = {
            "query": strip_boolean(query),
            "limit": min(options.limit, 100),
            "offset": options.offset,
            "fields": _FIELDS,
        }
        params.update(options.filters)
        headers = {"x-api-key": self._api_key} if self._api_key else None

        _wait_for_turn()
        response = get_response(
            "Semantic Scholar", f"{self._base_url}/paper/search",
            params=params, headers=headers, timeout=self._timeout, client=self._client,
        )
        payload = parse_json_object("Semantic Scholar", response)
        data = payload.get("data")
        if data is None and payload.get("total") == 0:
            return []
        if not isinstance(data, list):
            raise SearchProviderInvalidResponseError(
                "Semantic Scholar response is missing a 'data' list"
            )
        return [self._normalize(item) for item in data if isinstance(item, dict)]

    def _normalize(self, item: dict[str, Any]) -> NormalizedSearchResult:
        external_ids = item.get("externalIds") if isinstance(item.get("externalIds"), dict) else {}
        doi = external_ids.get("DOI")
        open_access = item.get("openAccessPdf") if isinstance(item.get("openAccessPdf"), dict) else {}
        pdf_url = open_access.get("url")
        url = pdf_url or (f"https://doi.org/{doi}" if doi else None) or item.get("url")

        authors = [
            a["name"]
            for a in (item.get("authors") or [])
            if isinstance(a, dict) and a.get("name")
        ]
        metadata: dict[str, Any] = {}
        if item.get("citationCount") is not None:
            metadata["cited_by_count"] = item["citationCount"]
        if external_ids.get("ArXiv"):
            metadata["arxiv_id"] = external_ids["ArXiv"]

        return NormalizedSearchResult(
            source=self.name,
            title=item.get("title"),
            authors=authors,
            abstract=item.get("abstract"),
            publication_year=item.get("year"),
            doi=doi,
            url=url,
            external_id=item.get("paperId"),
            metadata=metadata,
        )
