"""Tests for the Semantic Scholar SearchProvider adapter (RDA-066).

All HTTP calls are mocked via httpx.MockTransport: no test depends on the
real Semantic Scholar API.
"""

import httpx
import pytest

from app.core.config import settings
from app.schemas.search import NormalizedSearchResult, SearchOptions
from app.services.search import semantic_scholar as ss_module
from app.services.search.exceptions import (
    SearchProviderHTTPError,
    SearchProviderInvalidResponseError,
    SearchProviderRateLimitError,
    SearchProviderTimeoutError,
)
from app.services.search.semantic_scholar import SemanticScholarSearchProvider

FULL_PAPER = {
    "paperId": "649def34f8be52c8b66281af98ae884c09aef38",
    "title": "Construction of the Literature Graph in Semantic Scholar",
    "abstract": "We describe a deployed scalable system for organizing literature.",
    "year": 2018,
    "authors": [{"name": "Waleed Ammar"}, {"name": "Dirk Groeneveld"}],
    "externalIds": {"DOI": "10.18653/v1/N18-3011", "ArXiv": "1805.02262"},
    "openAccessPdf": {"url": "https://example.org/paper.pdf"},
    "url": "https://www.semanticscholar.org/paper/649def34",
    "citationCount": 100,
}

MINIMAL_PAPER = {"paperId": "abc123"}


@pytest.fixture(autouse=True)
def _reset_throttle_clock():
    """Every test starts as if no prior request happened (module-level state)."""
    ss_module._last_request_at = 0.0
    yield
    ss_module._last_request_at = 0.0


def make_provider(handler, *, api_key: str | None = None) -> SemanticScholarSearchProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return SemanticScholarSearchProvider(
        client=client, base_url="https://api.semanticscholar.org/graph/v1", api_key=api_key
    )


def json_response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def test_search_returns_normalized_results_with_full_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/graph/v1/paper/search"
        assert request.url.params["query"] == "literature graph"
        return json_response(200, {"data": [FULL_PAPER], "total": 1})

    provider = make_provider(handler)
    results = provider.search("literature graph")

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, NormalizedSearchResult)
    assert result.source == "semantic_scholar"
    assert result.title == "Construction of the Literature Graph in Semantic Scholar"
    assert result.authors == ["Waleed Ammar", "Dirk Groeneveld"]
    assert result.abstract.startswith("We describe a deployed")
    assert result.publication_year == 2018
    assert result.doi == "10.18653/v1/N18-3011"
    assert result.url == "https://example.org/paper.pdf"
    assert result.external_id == "649def34f8be52c8b66281af98ae884c09aef38"
    assert result.metadata == {"cited_by_count": 100, "arxiv_id": "1805.02262"}


def test_search_handles_missing_optional_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"data": [MINIMAL_PAPER], "total": 1})

    provider = make_provider(handler)
    results = provider.search("anything")

    assert len(results) == 1
    result = results[0]
    assert result.source == "semantic_scholar"
    assert result.title is None
    assert result.authors == []
    assert result.abstract is None
    assert result.publication_year is None
    assert result.doi is None
    assert result.url is None
    assert result.external_id == "abc123"
    assert result.metadata == {}


def test_search_handles_empty_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"total": 0})

    provider = make_provider(handler)
    results = provider.search("nonexistent query xyz")

    assert results == []


def test_search_raises_on_missing_data_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"total": 5})

    provider = make_provider(handler)
    with pytest.raises(SearchProviderInvalidResponseError):
        provider.search("query")


def test_search_raises_on_http_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    provider = make_provider(handler)
    with pytest.raises(SearchProviderHTTPError) as exc_info:
        provider.search("query")
    assert exc_info.value.status_code == 404


def test_search_raises_on_http_500() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "internal error"})

    provider = make_provider(handler)
    with pytest.raises(SearchProviderHTTPError) as exc_info:
        provider.search("query")
    assert exc_info.value.status_code == 500


def test_search_raises_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    provider = make_provider(handler)
    with pytest.raises(SearchProviderTimeoutError):
        provider.search("query")


def test_search_raises_on_invalid_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json{{{")

    provider = make_provider(handler)
    with pytest.raises(SearchProviderInvalidResponseError):
        provider.search("query")


def test_search_raises_on_rate_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    provider = make_provider(handler)
    with pytest.raises(SearchProviderRateLimitError):
        provider.search("query")


def test_search_skips_non_dict_items_in_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"data": [FULL_PAPER, "not-a-paper", None], "total": 3})

    provider = make_provider(handler)
    results = provider.search("query")

    assert len(results) == 1
    assert results[0].external_id == "649def34f8be52c8b66281af98ae884c09aef38"


def test_search_applies_pagination_params() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["limit"] = request.url.params["limit"]
        captured["offset"] = request.url.params["offset"]
        return json_response(200, {"data": [], "total": 0})

    provider = make_provider(handler)
    provider.search("query", SearchOptions(limit=10, offset=20))

    assert captured["limit"] == "10"
    assert captured["offset"] == "20"


def test_search_caps_limit_at_100() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["limit"] = request.url.params["limit"]
        return json_response(200, {"data": [], "total": 0})

    provider = make_provider(handler)
    provider.search("query", SearchOptions(limit=200))

    assert captured["limit"] == "100"


def test_search_strips_boolean_operators_from_query() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = request.url.params["query"]
        return json_response(200, {"data": [], "total": 0})

    provider = make_provider(handler)
    provider.search('("rare earth" OR REE) AND Brazil')

    assert captured["query"] == "rare earth REE Brazil"


def test_search_sends_api_key_header_when_configured() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["x-api-key"] = request.headers.get("x-api-key")
        return json_response(200, {"data": [], "total": 0})

    provider = make_provider(handler, api_key="test-key-123")
    provider.search("query")

    assert captured["x-api-key"] == "test-key-123"


def test_search_omits_api_key_header_when_not_configured() -> None:
    """api_key="" (not None): the provider treats None as "use settings",
    and settings.SEMANTIC_SCHOLAR_API_KEY may be a real key in this
    environment's .env, so the "no key" case must be forced explicitly."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["x-api-key"] = request.headers.get("x-api-key")
        return json_response(200, {"data": [], "total": 0})

    provider = make_provider(handler, api_key="")
    provider.search("query")

    assert captured["x-api-key"] is None


def test_search_throttles_consecutive_requests(monkeypatch) -> None:
    """Semantic Scholar enforces 1 req/s cumulative; the provider must space
    consecutive calls by SEMANTIC_SCHOLAR_MIN_INTERVAL_SECONDS regardless of
    how many provider instances are involved (module-level clock)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"data": [], "total": 0})

    sleeps: list[float] = []
    monkeypatch.setattr(ss_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    clock = {"t": 1000.0}
    monkeypatch.setattr(ss_module.time, "monotonic", lambda: clock["t"])

    provider = make_provider(handler)
    provider.search("first")
    assert sleeps == []  # first call never waits

    clock["t"] += 0.2  # well under the 1s minimum interval
    provider.search("second")

    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(
        settings.SEMANTIC_SCHOLAR_MIN_INTERVAL_SECONDS - 0.2
    )
