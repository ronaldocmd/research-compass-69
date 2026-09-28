"""CORE adapter for the SearchProvider contract (RDA-066).

CORE aggregates open-access full texts from institutional repositories
(including Brazilian ones). It requires a free API key; without one the
provider is simply not registered (see SearchService).
"""

from typing import Any

import httpx

from app.core.config import settings
from app.schemas.search import NormalizedSearchResult, SearchOptions
from app.services.search.common import get_response, parse_json_object
from app.services.search.exceptions import SearchProviderError, SearchProviderInvalidResponseError
from app.services.search.provider import SearchProvider


class CoreSearchProvider(SearchProvider):
    """SearchProvider adapter backed by the CORE v3 API."""

    name = "core"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = (base_url or settings.CORE_BASE_URL).rstrip("/")
        self._api_key = api_key if api_key is not None else settings.CORE_API_KEY
        if not self._api_key:
            raise SearchProviderError("CORE_API_KEY is not configured")
        self._timeout = timeout if timeout is not None else settings.CORE_TIMEOUT_SECONDS
        self._client = client

    def search(
        self, query: str, options: SearchOptions | None = None
    ) -> list[NormalizedSearchResult]:
        options = options or SearchOptions()
        params: dict[str, Any] = {
            "q": query,
            "limit": min(options.limit, 100),
            "offset": options.offset,
        }
        params.update(options.filters)

        response = get_response(
            "CORE", f"{self._base_url}/search/works/",
            params=params, headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self._timeout, client=self._client,
        )
        payload = parse_json_object("CORE", response)
        results = payload.get("results")
        if not isinstance(results, list):
            raise SearchProviderInvalidResponseError("CORE response is missing a 'results' list")
        return [self._normalize(item) for item in results if isinstance(item, dict)]

    def _normalize(self, item: dict[str, Any]) -> NormalizedSearchResult:
        doi = item.get("doi")
        download_url = item.get("downloadUrl")
        if not download_url:
            for link in item.get("links") or []:
                if isinstance(link, dict) and link.get("type") == "download" and link.get("url"):
                    download_url = link["url"]
                    break
        url = download_url or (f"https://doi.org/{doi}" if doi else None)

        authors = [
            a["name"]
            for a in (item.get("authors") or [])
            if isinstance(a, dict) and a.get("name")
        ]
        core_id = item.get("id")
        return NormalizedSearchResult(
            source=self.name,
            title=item.get("title"),
            authors=authors,
            abstract=item.get("abstract"),
            publication_year=item.get("yearPublished"),
            doi=doi,
            url=url,
            external_id=str(core_id) if core_id is not None else None,
            metadata={},
        )
