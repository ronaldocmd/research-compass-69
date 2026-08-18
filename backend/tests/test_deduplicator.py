"""Tests for SearchDeduplicator (RDA-016)."""

import pytest

from app.schemas.search import NormalizedSearchResult
from app.services.search.deduplicator import SearchDeduplicator


def result(**overrides) -> NormalizedSearchResult:
    defaults = dict(source="openalex", title="Some Title", publication_year=2020)
    defaults.update(overrides)
    return NormalizedSearchResult(**defaults)


def test_deduplicates_by_doi() -> None:
    a = result(source="openalex", doi="10.1000/xyz123", title="Title A")
    b = result(source="crossref", doi="10.1000/xyz123", title="Title B")

    deduped = SearchDeduplicator().deduplicate([a, b])

    assert len(deduped) == 1


def test_deduplicates_by_external_id() -> None:
    a = result(source="openalex", external_id="W123", title="Title A")
    b = result(source="crossref", external_id="W123", title="Title B")

    deduped = SearchDeduplicator().deduplicate([a, b])

    assert len(deduped) == 1


def test_deduplicates_by_normalized_url_http_vs_https() -> None:
    a = result(url="http://example.org/paper")
    b = result(url="https://example.org/paper")

    deduped = SearchDeduplicator().deduplicate([a, b])

    assert len(deduped) == 1


def test_deduplicates_by_normalized_url_trailing_slash() -> None:
    a = result(url="https://example.org/paper")
    b = result(url="https://example.org/paper/")

    deduped = SearchDeduplicator().deduplicate([a, b])

    assert len(deduped) == 1


def test_deduplicates_by_normalized_url_query_params() -> None:
    a = result(url="https://example.org/paper")
    b = result(url="https://example.org/paper?utm_source=x")

    deduped = SearchDeduplicator().deduplicate([a, b])

    assert len(deduped) == 1


def test_deduplicates_by_content_hash() -> None:
    a = result(
        title="Deep Learning for NLP",
        authors=["Ana Silva"],
        publication_year=2022,
        source="openalex",
    )
    b = result(
        title="  Deep Learning for NLP  ",
        authors=["Ana Silva"],
        publication_year=2022,
        source="crossref",
    )

    deduped = SearchDeduplicator().deduplicate([a, b])

    assert len(deduped) == 1


def test_does_not_deduplicate_similar_but_different_titles() -> None:
    a = result(title="Machine Learning in Medicine", authors=["Ana Silva"], publication_year=2021)
    b = result(
        title="Machine Learning in Medical Imaging", authors=["Ana Silva"], publication_year=2021
    )

    deduped = SearchDeduplicator().deduplicate([a, b])

    assert len(deduped) == 2


def test_does_not_deduplicate_same_title_different_year() -> None:
    a = result(title="Same Title", authors=["Ana Silva"], publication_year=2020)
    b = result(title="Same Title", authors=["Ana Silva"], publication_year=2021)

    deduped = SearchDeduplicator().deduplicate([a, b])

    assert len(deduped) == 2


def test_does_not_deduplicate_same_title_different_first_author() -> None:
    a = result(title="Same Title", authors=["Ana Silva"], publication_year=2020)
    b = result(title="Same Title", authors=["Bruno Souza"], publication_year=2020)

    deduped = SearchDeduplicator().deduplicate([a, b])

    assert len(deduped) == 2


def test_merges_complementary_fields_abstract_and_doi() -> None:
    a = result(
        source="openalex",
        doi=None,
        abstract="A rich abstract",
        external_id="W1",
    )
    b = result(
        source="crossref",
        doi="10.1000/xyz123",
        abstract=None,
        external_id="W1",
    )

    deduped = SearchDeduplicator().deduplicate([a, b])

    assert len(deduped) == 1
    merged = deduped[0]
    assert merged.abstract == "A rich abstract"
    assert merged.doi == "10.1000/xyz123"


def test_merges_metadata_from_both_sources() -> None:
    a = result(
        source="openalex",
        external_id="W1",
        metadata={"cited_by_count": 10},
    )
    b = result(
        source="crossref",
        external_id="W1",
        metadata={"is_referenced_by_count": 5},
    )

    deduped = SearchDeduplicator().deduplicate([a, b])

    merged_metadata = deduped[0].metadata
    assert merged_metadata["cited_by_count"] == 10
    assert merged_metadata["is_referenced_by_count"] == 5
    assert set(merged_metadata["merged_sources"]) == {"openalex", "crossref"}


def test_default_provider_preference_prefers_openalex() -> None:
    openalex_result = result(source="openalex", external_id="W1", title="OpenAlex Title")
    crossref_result = result(source="crossref", external_id="W1", title="Crossref Title")

    deduped = SearchDeduplicator().deduplicate([crossref_result, openalex_result])

    assert len(deduped) == 1
    assert deduped[0].source == "openalex"
    assert deduped[0].title == "OpenAlex Title"


def test_custom_provider_preference_can_prefer_crossref() -> None:
    openalex_result = result(source="openalex", external_id="W1", title="OpenAlex Title")
    crossref_result = result(source="crossref", external_id="W1", title="Crossref Title")

    deduplicator = SearchDeduplicator(provider_preference=["crossref", "openalex"])
    deduped = deduplicator.deduplicate([openalex_result, crossref_result])

    assert len(deduped) == 1
    assert deduped[0].source == "crossref"
    assert deduped[0].title == "Crossref Title"


def test_empty_list_returns_empty_list() -> None:
    assert SearchDeduplicator().deduplicate([]) == []


def test_list_without_duplicates_is_unchanged_in_length() -> None:
    a = result(doi="10.1000/a", title="Title A")
    b = result(doi="10.1000/b", title="Title B")
    c = result(doi="10.1000/c", title="Title C")

    deduped = SearchDeduplicator().deduplicate([a, b, c])

    assert len(deduped) == 3


def test_all_results_duplicated_collapses_to_one() -> None:
    results = [result(doi="10.1000/same", title=f"Variant {i}") for i in range(5)]

    deduped = SearchDeduplicator().deduplicate(results)

    assert len(deduped) == 1


def test_unknown_strategy_raises_value_error() -> None:
    with pytest.raises(ValueError):
        SearchDeduplicator().deduplicate([result()], strategy="fuzzy")


def test_results_with_no_identity_signal_are_not_merged() -> None:
    a = NormalizedSearchResult(source="openalex")
    b = NormalizedSearchResult(source="crossref")

    deduped = SearchDeduplicator().deduplicate([a, b])

    assert len(deduped) == 2
