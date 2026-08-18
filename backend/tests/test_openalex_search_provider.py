"""Tests for the OpenAlex SearchProvider adapter (RDA-012).

All HTTP calls are mocked via httpx.MockTransport: no test depends on the
real OpenAlex API.
"""

import json

import httpx
import pytest

from app.schemas.search import NormalizedSearchResult, SearchOptions
from app.services.search.exceptions import (
    SearchProviderHTTPError,
    SearchProviderInvalidResponseError,
    SearchProviderRateLimitError,
    SearchProviderTimeoutError,
)
from app.services.search.openalex import OpenAlexSearchProvider

FULL_WORK = {
    "id": "https://openalex.org/W2741809807",
    "doi": "https://doi.org/10.7717/peerj.4375",
    "title": "The state of OA: a large-scale analysis",
    "display_name": "The state of OA: a large-scale analysis",
    "publication_year": 2018,
    "type": "article",
    "cited_by_count": 42,
    "authorships": [
        {"author": {"id": "https://openalex.org/A1", "display_name": "Heather Piwowar"}},
        {"author": {"id": "https://openalex.org/A2", "display_name": "Jason Priem"}},
    ],
    "abstract_inverted_index": {
        "Open": [0],
        "access": [1],
        "is": [2],
        "growing.": [3],
    },
    "primary_location": {"landing_page_url": "https://peerj.com/articles/4375"},
}

MINIMAL_WORK = {
    "id": "https://openalex.org/W999",
}


def make_provider(handler) -> OpenAlexSearchProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return OpenAlexSearchProvider(client=client, base_url="https://api.openalex.org")


def json_response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def test_search_returns_normalized_results_with_full_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/works"
        assert request.url.params["search"] == "open access"
        return json_response(200, {"results": [FULL_WORK]})

    provider = make_provider(handler)
    results = provider.search("open access")

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, NormalizedSearchResult)
    assert result.source == "openalex"
    assert result.title == "The state of OA: a large-scale analysis"
    assert result.authors == ["Heather Piwowar", "Jason Priem"]
    assert result.abstract == "Open access is growing."
    assert result.publication_year == 2018
    assert result.doi == "10.7717/peerj.4375"
    assert result.url == "https://doi.org/10.7717/peerj.4375"
    assert result.external_id == "https://openalex.org/W2741809807"
    assert result.metadata == {"type": "article", "cited_by_count": 42}


def test_search_handles_missing_optional_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"results": [MINIMAL_WORK]})

    provider = make_provider(handler)
    results = provider.search("anything")

    assert len(results) == 1
    result = results[0]
    assert result.source == "openalex"
    assert result.title is None
    assert result.authors == []
    assert result.abstract is None
    assert result.publication_year is None
    assert result.doi is None
    assert result.url == "https://openalex.org/W999"
    assert result.external_id == "https://openalex.org/W999"
    assert result.metadata == {}


def test_search_handles_empty_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"results": []})

    provider = make_provider(handler)
    results = provider.search("nonexistent query xyz")

    assert results == []


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


def test_search_raises_on_missing_results_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"meta": {"count": 0}})

    provider = make_provider(handler)
    with pytest.raises(SearchProviderInvalidResponseError):
        provider.search("query")


def test_search_applies_pagination_params() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["per_page"] = request.url.params["per-page"]
        captured["page"] = request.url.params["page"]
        return json_response(200, {"results": []})

    provider = make_provider(handler)
    provider.search("query", SearchOptions(limit=10, offset=20))

    assert captured["per_page"] == "10"
    assert captured["page"] == "3"


def test_search_first_page_has_offset_zero() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["page"] = request.url.params["page"]
        return json_response(200, {"results": []})

    provider = make_provider(handler)
    provider.search("query", SearchOptions(limit=25, offset=0))

    assert captured["page"] == "1"


def test_search_includes_mailto_when_email_configured() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["mailto"] = request.url.params.get("mailto")
        return json_response(200, {"results": []})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    provider = OpenAlexSearchProvider(
        client=client, base_url="https://api.openalex.org", email="team@example.com"
    )
    provider.search("query")

    assert captured["mailto"] == "team@example.com"


def test_search_skips_non_dict_items_in_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"results": [FULL_WORK, "not-a-work", None]})

    provider = make_provider(handler)
    results = provider.search("query")

    assert len(results) == 1
    assert results[0].external_id == "https://openalex.org/W2741809807"
