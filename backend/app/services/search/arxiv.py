"""arXiv adapter for the SearchProvider contract (RDA-066).

arXiv answers with an Atom feed. Every entry carries a direct PDF link, so
results from this source are always downloadable. The feed is parsed with the
standard library after rejecting DTD/entity declarations (entity-expansion
attacks), since ElementTree expands internal entities.
"""

import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.search import NormalizedSearchResult, SearchOptions
from app.services.search.common import get_response, to_arxiv_query
from app.services.search.exceptions import (
    SearchProviderError,
    SearchProviderHTTPError,
    SearchProviderInvalidResponseError,
    SearchProviderRateLimitError,
)
from app.services.search.provider import SearchProvider

logger = logging.getLogger(__name__)

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"
_VERSION_SUFFIX = re.compile(r"v\d+$")

# Process-wide throttle: SearchService builds new provider instances per run and
# several runs/queries can overlap, so the clock lives at module level.
_throttle_lock = threading.Lock()
_last_request_at = 0.0
# arXiv answers a refused burst with 406 (seen in production) or 429/503.
_RETRYABLE_STATUS = {406, 429, 503}

# Process-wide circuit breaker (RDA-067), same rationale as the throttle
# above: shared at module level so it protects across provider instances.
_breaker_lock = threading.Lock()
_consecutive_failures = 0
_breaker_open_until = 0.0  # monotonic time; 0.0 means closed


def _wait_for_turn() -> None:
    """Block until ``ARXIV_MIN_INTERVAL_SECONDS`` passed since the last request."""
    global _last_request_at
    with _throttle_lock:
        wait = settings.ARXIV_MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def _breaker_blocked() -> bool:
    with _breaker_lock:
        return bool(_breaker_open_until) and time.monotonic() < _breaker_open_until


def _breaker_record_success() -> None:
    global _consecutive_failures, _breaker_open_until
    with _breaker_lock:
        if _consecutive_failures or _breaker_open_until:
            logger.info("arXiv circuit breaker reset after a successful request")
        _consecutive_failures = 0
        _breaker_open_until = 0.0


def _breaker_record_failure() -> None:
    global _consecutive_failures, _breaker_open_until
    with _breaker_lock:
        _consecutive_failures += 1
        if _consecutive_failures >= settings.ARXIV_BREAKER_FAILURE_THRESHOLD:
            _breaker_open_until = time.monotonic() + settings.ARXIV_BREAKER_COOLDOWN_SECONDS
            logger.warning(
                "arXiv circuit breaker OPEN after %d consecutive failures; "
                "skipping arXiv requests for %.0fs",
                _consecutive_failures, settings.ARXIV_BREAKER_COOLDOWN_SECONDS,
            )


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip() or None


class ArxivSearchProvider(SearchProvider):
    """SearchProvider adapter backed by the arXiv API."""

    name = "arxiv"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = (base_url or settings.ARXIV_BASE_URL).rstrip("/")
        self._timeout = timeout if timeout is not None else settings.ARXIV_TIMEOUT_SECONDS
        self._client = client

    def search(
        self, query: str, options: SearchOptions | None = None
    ) -> list[NormalizedSearchResult]:
        if _breaker_blocked():
            raise SearchProviderError(
                "arXiv circuit breaker open (too many recent failures); "
                "skipping until it has had time to recover"
            )
        options = options or SearchOptions()
        params: dict[str, Any] = {
            "search_query": to_arxiv_query(query),
            "start": options.offset,
            "max_results": options.limit,
            "sortBy": "relevance",
        }
        params.update(options.filters)

        try:
            response = self._get(params)
            body = response.text
            if "<!DOCTYPE" in body or "<!ENTITY" in body:
                raise SearchProviderInvalidResponseError("arXiv returned an unsafe XML document")
            try:
                root = ET.fromstring(body)
            except ET.ParseError as exc:
                raise SearchProviderInvalidResponseError("arXiv returned invalid XML") from exc
        except Exception:
            _breaker_record_failure()
            raise
        _breaker_record_success()
        return [self._normalize(entry) for entry in root.findall(f"{_ATOM}entry")]

    def _get(self, params: dict[str, Any]):
        """GET with process-wide spacing and one retry when arXiv refuses a burst."""
        for attempt in (1, 2):
            _wait_for_turn()
            try:
                return get_response(
                    "arXiv", f"{self._base_url}/api/query",
                    params=params, timeout=self._timeout, client=self._client,
                )
            except (SearchProviderRateLimitError, SearchProviderHTTPError) as exc:
                refused = isinstance(exc, SearchProviderRateLimitError) or (
                    exc.status_code in _RETRYABLE_STATUS
                )
                if not refused or attempt == 2:
                    raise
            time.sleep(settings.ARXIV_RETRY_DELAY_SECONDS)
        raise AssertionError("unreachable")  # pragma: no cover

    def _normalize(self, entry: ET.Element) -> NormalizedSearchResult:
        abs_url = _clean(entry.findtext(f"{_ATOM}id"))
        arxiv_id = _VERSION_SUFFIX.sub("", abs_url.rsplit("/abs/", 1)[-1]) if abs_url else None

        pdf_url = None
        for link in entry.findall(f"{_ATOM}link"):
            if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                pdf_url = link.get("href")
                break
        if pdf_url is None and arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

        published = _clean(entry.findtext(f"{_ATOM}published")) or ""
        year = int(published[:4]) if published[:4].isdigit() else None

        authors = [
            name
            for name in (_clean(a.findtext(f"{_ATOM}name")) for a in entry.findall(f"{_ATOM}author"))
            if name
        ]
        metadata: dict[str, Any] = {}
        category = entry.find(f"{_ATOM}category")
        if category is not None and category.get("term"):
            metadata["primary_category"] = category.get("term")

        return NormalizedSearchResult(
            source=self.name,
            title=_clean(entry.findtext(f"{_ATOM}title")),
            authors=authors,
            abstract=_clean(entry.findtext(f"{_ATOM}summary")),
            publication_year=year,
            doi=_clean(entry.findtext(f"{_ARXIV}doi")),
            url=pdf_url or abs_url,
            external_id=arxiv_id,
            metadata=metadata,
        )
