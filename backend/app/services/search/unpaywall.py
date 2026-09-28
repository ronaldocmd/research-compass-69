"""Unpaywall enrichment (RDA-066).

Not a search source: given results that carry a DOI but no direct PDF link
(typically a ``doi.org`` landing page that answers 403/anti-bot, RDA-060), it
looks up the best open-access copy and swaps the URL for it. Failures are
per-DOI and silent, so enrichment can only improve a result, never lose one.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.schemas.search import NormalizedSearchResult
from app.services.search.common import get_response, is_pdf_url, parse_json_object
from app.services.search.exceptions import SearchProviderError

logger = logging.getLogger(__name__)

_MAX_WORKERS = 5


class UnpaywallEnricher:
    def __init__(
        self,
        *,
        email: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._email = email if email is not None else settings.UNPAYWALL_EMAIL
        self._base_url = (base_url or settings.UNPAYWALL_BASE_URL).rstrip("/")
        self._timeout = timeout if timeout is not None else settings.UNPAYWALL_TIMEOUT_SECONDS
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self._email)

    def enrich(self, results: list[NormalizedSearchResult]) -> list[NormalizedSearchResult]:
        """Return ``results`` with PDF links filled in where Unpaywall knows one."""
        if not self.enabled:
            return results
        targets = [i for i, r in enumerate(results) if r.doi and not is_pdf_url(r.url)]
        if not targets:
            return results
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            pdf_urls = list(pool.map(lambda i: self._lookup(results[i].doi), targets))
        enriched = list(results)
        for index, pdf_url in zip(targets, pdf_urls):
            if pdf_url:
                current = enriched[index]
                enriched[index] = current.model_copy(
                    update={
                        "url": pdf_url,
                        "metadata": {**current.metadata, "oa_source": "unpaywall"},
                    }
                )
        return enriched

    def _lookup(self, doi: str) -> str | None:
        try:
            response = get_response(
                "Unpaywall", f"{self._base_url}/{quote(doi, safe='/')}",
                params={"email": self._email}, timeout=self._timeout, client=self._client,
            )
            payload = parse_json_object("Unpaywall", response)
        except SearchProviderError as exc:
            logger.debug("Unpaywall lookup skipped for %s: %s", doi, exc)
            return None
        # Best location first, then any other open copy that links a PDF.
        locations = [payload.get("best_oa_location"), *(payload.get("oa_locations") or [])]
        for location in locations:
            if isinstance(location, dict) and location.get("url_for_pdf"):
                return location["url_for_pdf"]
        return None
