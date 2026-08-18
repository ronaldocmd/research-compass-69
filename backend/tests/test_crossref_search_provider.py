"""Tests for the Crossref SearchProvider adapter (RDA-013).

All HTTP calls are mocked via httpx.MockTransport: no test depends on the
real Crossref API.
"""

import httpx
import pytest

from app.schemas.search import NormalizedSearchResult, SearchOptions
from app.services.search.crossref import CrossrefSearchProvider
from app.services.search.exceptions import (
    SearchProviderHTTPError,
    SearchProviderInvalidResponseError,
    SearchProviderRateLimitError,
    SearchProviderTimeoutError,
)

FULL_WORK = {
    "DOI": "10.1000/xyz123",
    "title": ["Deep Learning for NLP"],
    "author": [
        {"given": "Ana", "family": "Silva"},
        {"given": "Bruno", "family": "Souza"},
    ],
    "published": {"date-parts": [[2023, 5, 1]]},
    "type": "journal-article",
    "is-referenced-by-count": 17,
    "abstract": "<jats:p>An overview of deep learning applied to NLP.</jats:p>",
    "resource": {"primary": {"URL": "https://example.org/xyz123"}},
    "link": [{"URL": "https://example.org/alt-link"}],
}

MINIMAL_WORK = {
    "DOI": "10.1000/minimal",
}


def make_provider(handler) -> CrossrefSearchProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return CrossrefSearchProvider(client=client, base_url="https://api.crossref.org")


def json_response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def test_search_returns_normalized_results_with_full_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/works"
        assert request.url.params["query"] == "deep learning"
        return json_response(200, {"message": {"items": [FULL_WORK]}})

    provider = make_provider(handler)
    results = provider.search("deep learning")

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, NormalizedSearchResult)
    assert result.source == "crossref"
    assert result.title == "Deep Learning for NLP"
    assert result.authors == ["Ana Silva", "Bruno Souza"]
    assert result.publication_year == 2023
    assert result.doi == "10.1000/xyz123"
    assert result.url == "https://example.org/xyz123"
    assert result.external_id == "10.1000/xyz123"
    assert result.abstract == "<jats:p>An overview of deep learning applied to NLP.</jats:p>"
    assert result.metadata == {"type": "journal-article", "is_referenced_by_count": 17}


def test_search_handles_missing_optional_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"message": {"items": [MINIMAL_WORK]}})

    provider = make_provider(handler)
    results = provider.search("anything")

    assert len(results) == 1
    result = results[0]
    assert result.source == "crossref"
    assert result.title is None
    assert result.authors == []
    assert result.abstract is None
    assert result.publication_year is None
    assert result.doi == "10.1000/minimal"
    assert result.url == "https://doi.org/10.1000/minimal"
    assert result.external_id == "10.1000/minimal"
    assert result.metadata == {}


def test_search_handles_empty_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"message": {"items": []}})

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


def test_search_raises_on_missing_message_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"status": "ok"})

    provider = make_provider(handler)
    with pytest.raises(SearchProviderInvalidResponseError):
        provider.search("query")


def test_search_raises_on_missing_items_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"message": {"total-results": 0}})

    provider = make_provider(handler)
    with pytest.raises(SearchProviderInvalidResponseError):
        provider.search("query")


def test_search_applies_pagination_params() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["rows"] = request.url.params["rows"]
        captured["offset"] = request.url.params["offset"]
        return json_response(200, {"message": {"items": []}})

    provider = make_provider(handler)
    provider.search("query", SearchOptions(limit=10, offset=20))

    assert captured["rows"] == "10"
    assert captured["offset"] == "20"


def test_search_includes_mailto_when_email_configured() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["mailto"] = request.url.params.get("mailto")
        return json_response(200, {"message": {"items": []}})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    provider = CrossrefSearchProvider(
        client=client, base_url="https://api.crossref.org", email="team@example.com"
    )
    provider.search("query")

    assert captured["mailto"] == "team@example.com"


def test_search_handles_missing_date_fields() -> None:
    work = {"DOI": "10.1000/no-date", "title": ["No date work"]}

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"message": {"items": [work]}})

    provider = make_provider(handler)
    results = provider.search("query")

    assert results[0].publication_year is None


def test_search_handles_malformed_date_fields() -> None:
    work = {
        "DOI": "10.1000/bad-date",
        "title": ["Bad date work"],
        "published": {"date-parts": [[]]},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"message": {"items": [work]}})

    provider = make_provider(handler)
    results = provider.search("query")

    assert results[0].publication_year is None


def test_search_falls_back_to_created_date_when_published_missing() -> None:
    work = {
        "DOI": "10.1000/created-date",
        "title": ["Created date work"],
        "created": {"date-parts": [[2019, 3, 4]]},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"message": {"items": [work]}})

    provider = make_provider(handler)
    results = provider.search("query")

    assert results[0].publication_year == 2019


def test_search_handles_missing_authors() -> None:
    work = {"DOI": "10.1000/no-authors", "title": ["No authors work"]}

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"message": {"items": [work]}})

    provider = make_provider(handler)
    results = provider.search("query")

    assert results[0].authors == []


def test_search_uses_author_name_field_when_given_family_absent() -> None:
    work = {
        "DOI": "10.1000/org-author",
        "title": ["Organization authored work"],
        "author": [{"name": "World Health Organization"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"message": {"items": [work]}})

    provider = make_provider(handler)
    results = provider.search("query")

    assert results[0].authors == ["World Health Organization"]


def test_search_skips_non_dict_items_in_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"message": {"items": [FULL_WORK, "not-a-work", None]}})

    provider = make_provider(handler)
    results = provider.search("query")

    assert len(results) == 1
    assert results[0].external_id == "10.1000/xyz123"
