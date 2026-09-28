"""Europe PMC adapter for the SearchProvider contract (RDA-066).

Europe PMC natively supports the planner's boolean syntax (AND/OR, quoted
phrases). Open-access records expose full-text PDF links, which are preferred
over landing pages so the downloader can fetch the document.
"""

from typing import Any

import httpx

from app.core.config import settings
from app.schemas.search import NormalizedSearchResult, SearchOptions
from app.services.search.common import get_response, parse_json_object, strip_tags
from app.services.search.exceptions import SearchProviderInvalidResponseError
from app.services.search.provider import SearchProvider

_OPEN = {"open access", "free"}


class EuropePMCSearchProvider(SearchProvider):
    """SearchProvider adapter backed by the Europe PMC REST API."""

    name = "europe_pmc"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = (base_url or settings.EUROPE_PMC_BASE_URL).rstrip("/")
        self._timeout = timeout if timeout is not None else settings.EUROPE_PMC_TIMEOUT_SECONDS
        self._client = client

    def search(
        self, query: str, options: SearchOptions | None = None
    ) -> list[NormalizedSearchResult]:
        options = options or SearchOptions()
        params: dict[str, Any] = {
            "query": query,
            "format": "json",
            "resultType": "core",
            "pageSize": min(options.limit, 100),
            "page": (options.offset // options.limit) + 1,
        }
        params.update(options.filters)

        response = get_response(
            "Europe PMC", f"{self._base_url}/search",
            params=params, timeout=self._timeout, client=self._client,
        )
        payload = parse_json_object("Europe PMC", response)
        result_list = payload.get("resultList")
        results = result_list.get("result") if isinstance(result_list, dict) else None
        if not isinstance(results, list):
            raise SearchProviderInvalidResponseError(
                "Europe PMC response is missing 'resultList.result'"
            )
        return [self._normalize(item) for item in results if isinstance(item, dict)]

    def _normalize(self, item: dict[str, Any]) -> NormalizedSearchResult:
        doi = item.get("doi")
        pmcid = item.get("pmcid")

        pdf_url = None
        urls = (item.get("fullTextUrlList") or {}).get("fullTextUrl") or []
        for entry in urls:
            if (
                isinstance(entry, dict)
                and str(entry.get("documentStyle", "")).lower() == "pdf"
                and str(entry.get("availability", "")).lower() in _OPEN
            ):
                pdf_url = entry.get("url")
                break
        if pdf_url is None and pmcid and item.get("isOpenAccess") == "Y":
            pdf_url = f"https://europepmc.org/articles/{pmcid}?pdf=render"

        source, record_id = item.get("source"), item.get("id")
        url = pdf_url or (f"https://doi.org/{doi}" if doi else None) or (
            f"https://europepmc.org/article/{source}/{record_id}" if source and record_id else None
        )

        author_string = item.get("authorString") or ""
        authors = [a.strip().rstrip(".") for a in author_string.split(",") if a.strip().rstrip(".")]

        year = item.get("pubYear")
        metadata: dict[str, Any] = {}
        if item.get("citedByCount") is not None:
            metadata["cited_by_count"] = item["citedByCount"]
        if pmcid:
            metadata["pmcid"] = pmcid
        if item.get("isOpenAccess"):
            metadata["is_open_access"] = item["isOpenAccess"] == "Y"

        return NormalizedSearchResult(
            source=self.name,
            title=strip_tags(item.get("title")),
            authors=authors,
            abstract=strip_tags(item.get("abstractText")),
            publication_year=int(year) if isinstance(year, str) and year.isdigit() else year,
            doi=doi,
            url=url,
            external_id=f"{source}:{record_id}" if source and record_id else None,
            metadata=metadata,
        )
