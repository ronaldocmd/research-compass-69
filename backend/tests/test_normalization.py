"""Tests for result normalization (RDA-015).

Covers both layers added by RDA-015:
- the pure helper functions in app.services.search.normalizer
- the automatic validation they power inside NormalizedSearchResult

No test depends on the real OpenAlex/Crossref APIs.
"""

import httpx
import pytest

from app.schemas.search import NormalizedSearchResult
from app.services.search.crossref import CrossrefSearchProvider
from app.services.search.normalizer import (
    MAX_PUBLICATION_YEAR,
    MIN_PUBLICATION_YEAR,
    normalize_abstract,
    normalize_authors,
    normalize_doi,
    normalize_title,
    normalize_url,
    normalize_year,
)
from app.services.search.openalex import OpenAlexSearchProvider

# ---------------------------------------------------------------------------
# normalize_title
# ---------------------------------------------------------------------------


def test_normalize_title_strips_whitespace() -> None:
    assert normalize_title("  Deep Learning  ") == "Deep Learning"


def test_normalize_title_blank_becomes_none() -> None:
    assert normalize_title("   ") is None
    assert normalize_title("") is None


def test_normalize_title_non_string_becomes_none() -> None:
    assert normalize_title(None) is None
    assert normalize_title(123) is None


# ---------------------------------------------------------------------------
# normalize_authors
# ---------------------------------------------------------------------------


def test_normalize_authors_strips_and_drops_blanks() -> None:
    assert normalize_authors([" Ana Silva ", "", "   ", "Bruno"]) == ["Ana Silva", "Bruno"]


def test_normalize_authors_non_list_becomes_empty_list() -> None:
    assert normalize_authors(None) == []
    assert normalize_authors("Ana Silva") == []


def test_normalize_authors_drops_non_string_entries() -> None:
    assert normalize_authors(["Ana", 42, None, {"name": "x"}]) == ["Ana"]


# ---------------------------------------------------------------------------
# normalize_abstract
# ---------------------------------------------------------------------------


def test_normalize_abstract_strips_and_blanks_to_none() -> None:
    assert normalize_abstract("  some text  ") == "some text"
    assert normalize_abstract("   ") is None
    assert normalize_abstract(None) is None


# ---------------------------------------------------------------------------
# normalize_year
# ---------------------------------------------------------------------------


def test_normalize_year_accepts_valid_int() -> None:
    assert normalize_year(2023) == 2023


def test_normalize_year_accepts_numeric_string() -> None:
    assert normalize_year("2023") == 2023


def test_normalize_year_rejects_negative() -> None:
    assert normalize_year(-100) is None


def test_normalize_year_rejects_too_far_future() -> None:
    assert normalize_year(MAX_PUBLICATION_YEAR + 1) is None


def test_normalize_year_accepts_range_boundaries() -> None:
    assert normalize_year(MIN_PUBLICATION_YEAR) == MIN_PUBLICATION_YEAR
    assert normalize_year(MAX_PUBLICATION_YEAR) == MAX_PUBLICATION_YEAR


def test_normalize_year_rejects_bool() -> None:
    assert normalize_year(True) is None


def test_normalize_year_rejects_non_numeric() -> None:
    assert normalize_year("not a year") is None
    assert normalize_year(None) is None


# ---------------------------------------------------------------------------
# normalize_doi
# ---------------------------------------------------------------------------


def test_normalize_doi_accepts_bare_doi() -> None:
    assert normalize_doi("10.1000/xyz123") == "10.1000/xyz123"


def test_normalize_doi_strips_https_prefix() -> None:
    assert normalize_doi("https://doi.org/10.1000/xyz123") == "10.1000/xyz123"


def test_normalize_doi_rejects_malformed() -> None:
    assert normalize_doi("not-a-doi") is None
    assert normalize_doi("10.abc/xyz") is None


def test_normalize_doi_rejects_non_string() -> None:
    assert normalize_doi(None) is None
    assert normalize_doi(12345) is None


# ---------------------------------------------------------------------------
# normalize_url
# ---------------------------------------------------------------------------


def test_normalize_url_accepts_http_and_https() -> None:
    assert normalize_url("https://example.org/x") == "https://example.org/x"
    assert normalize_url("http://example.org/x") == "http://example.org/x"


def test_normalize_url_rejects_malformed() -> None:
    assert normalize_url("not a url") is None
    assert normalize_url("ftp://example.org/x") is None
    assert normalize_url("") is None


def test_normalize_url_rejects_non_string() -> None:
    assert normalize_url(None) is None


# ---------------------------------------------------------------------------
# NormalizedSearchResult end-to-end validation
# ---------------------------------------------------------------------------


def test_invalid_values_are_normalized_not_raised() -> None:
    result = NormalizedSearchResult(
        source="openalex",
        title="  ",
        publication_year=-5,
        doi="not-a-doi",
        url="not a url",
    )

    assert result.title is None
    assert result.publication_year is None
    assert result.doi is None
    assert result.url is None


def test_invalid_values_are_preserved_in_metadata() -> None:
    result = NormalizedSearchResult(
        source="openalex",
        publication_year=99999,
        doi="not-a-doi",
        url="not a url",
    )

    assert result.metadata["raw_publication_year"] == 99999
    assert result.metadata["raw_doi"] == "not-a-doi"
    assert result.metadata["raw_url"] == "not a url"


def test_valid_values_are_not_added_to_metadata() -> None:
    result = NormalizedSearchResult(
        source="openalex",
        publication_year=2020,
        doi="10.1000/xyz123",
        url="https://example.org/x",
    )

    assert "raw_publication_year" not in result.metadata
    assert "raw_doi" not in result.metadata
    assert "raw_url" not in result.metadata


def test_existing_metadata_is_preserved_alongside_raw_values() -> None:
    result = NormalizedSearchResult(
        source="openalex",
        doi="bad-doi",
        metadata={"type": "article"},
    )

    assert result.metadata["type"] == "article"
    assert result.metadata["raw_doi"] == "bad-doi"


def test_all_fields_none_produces_valid_result() -> None:
    result = NormalizedSearchResult(source="crossref")

    assert result.title is None
    assert result.authors == []
    assert result.abstract is None
    assert result.publication_year is None
    assert result.doi is None
    assert result.url is None
    assert result.external_id is None
    assert result.metadata == {}


def test_same_input_produces_same_output_idempotent() -> None:
    payload = dict(
        source="openalex",
        title="  Some Title  ",
        authors=[" Ana ", ""],
        publication_year=2020,
        doi="https://doi.org/10.1000/xyz123",
        url="https://example.org/x",
    )

    result_a = NormalizedSearchResult(**payload)
    result_b = NormalizedSearchResult(**payload)

    assert result_a == result_b
    assert result_a.title == "Some Title"
    assert result_a.authors == ["Ana"]
    assert result_a.doi == "10.1000/xyz123"


def test_source_is_required() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        NormalizedSearchResult()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Cross-provider consistency (OpenAlex vs Crossref)
# ---------------------------------------------------------------------------


def _search_with_mock(provider_cls, base_url: str, payload: dict, query: str = "query"):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    provider = provider_cls(client=client, base_url=base_url)
    return provider.search(query)


def test_openalex_and_crossref_results_share_same_shape_for_missing_fields() -> None:
    openalex_results = _search_with_mock(
        OpenAlexSearchProvider,
        "https://api.openalex.org",
        {"results": [{"id": "https://openalex.org/W1"}]},
    )
    crossref_results = _search_with_mock(
        CrossrefSearchProvider,
        "https://api.crossref.org",
        {"message": {"items": [{"DOI": "10.1000/minimal"}]}},
    )

    openalex_result = openalex_results[0]
    crossref_result = crossref_results[0]

    for result in (openalex_result, crossref_result):
        assert result.title is None
        assert result.authors == []
        assert result.abstract is None
        assert result.publication_year is None
        assert isinstance(result.metadata, dict)

    assert openalex_result.source == "openalex"
    assert crossref_result.source == "crossref"


def test_openalex_and_crossref_both_reject_invalid_year_consistently() -> None:
    openalex_results = _search_with_mock(
        OpenAlexSearchProvider,
        "https://api.openalex.org",
        {"results": [{"id": "https://openalex.org/W1", "publication_year": 30000}]},
    )
    crossref_results = _search_with_mock(
        CrossrefSearchProvider,
        "https://api.crossref.org",
        {
            "message": {
                "items": [
                    {"DOI": "10.1000/x", "published": {"date-parts": [[30000]]}}
                ]
            }
        },
    )

    assert openalex_results[0].publication_year is None
    assert openalex_results[0].metadata["raw_publication_year"] == 30000
    assert crossref_results[0].publication_year is None
    assert crossref_results[0].metadata["raw_publication_year"] == 30000
