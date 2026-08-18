"""Tests for the search provider abstraction (RDA-011).

Covers only the contract itself (SearchProvider, SearchOptions and
NormalizedSearchResult): no concrete provider (OpenAlex, Crossref, ...)
exists yet, so a minimal fake provider is used to exercise the interface.
"""

import pytest
from pydantic import ValidationError

from app.schemas.search import NormalizedSearchResult, SearchOptions
from app.services.search import SearchProvider


class FakeSearchProvider(SearchProvider):
    """Minimal concrete SearchProvider used only to exercise the contract."""

    name = "fake"

    def search(self, query: str, options: SearchOptions | None = None) -> list[NormalizedSearchResult]:
        options = options or SearchOptions()
        return [
            NormalizedSearchResult(
                source=self.name,
                title=f"Result for {query}",
                external_id="1",
            )
        ][: options.limit]


def test_search_provider_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        SearchProvider()  # type: ignore[abstract]


def test_concrete_provider_implements_search() -> None:
    provider = FakeSearchProvider()
    results = provider.search("machine learning")

    assert isinstance(results, list)
    assert len(results) == 1
    assert isinstance(results[0], NormalizedSearchResult)
    assert results[0].title == "Result for machine learning"
    assert results[0].source == "fake"


def test_provider_without_search_method_cannot_be_instantiated() -> None:
    class IncompleteProvider(SearchProvider):
        name = "incomplete"

    with pytest.raises(TypeError):
        IncompleteProvider()  # type: ignore[abstract]


def test_search_options_defaults() -> None:
    options = SearchOptions()

    assert options.limit == 20
    assert options.offset == 0
    assert options.filters == {}


def test_search_options_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SearchOptions(unknown_field="x")


def test_search_options_rejects_invalid_limit() -> None:
    with pytest.raises(ValidationError):
        SearchOptions(limit=0)
    with pytest.raises(ValidationError):
        SearchOptions(limit=201)


def test_search_options_accepts_custom_values() -> None:
    options = SearchOptions(limit=10, offset=5, filters={"year": 2024})

    assert options.limit == 10
    assert options.offset == 5
    assert options.filters == {"year": 2024}


def test_normalized_search_result_requires_source_only() -> None:
    result = NormalizedSearchResult(source="openalex")

    assert result.source == "openalex"
    assert result.title is None
    assert result.authors == []
    assert result.abstract is None
    assert result.publication_year is None
    assert result.doi is None
    assert result.url is None
    assert result.external_id is None
    assert result.metadata == {}


def test_normalized_search_result_source_is_required() -> None:
    with pytest.raises(ValidationError):
        NormalizedSearchResult()  # type: ignore[call-arg]


def test_normalized_search_result_accepts_full_payload() -> None:
    result = NormalizedSearchResult(
        source="crossref",
        title="Deep Learning for NLP",
        authors=["Ana Silva", "Bruno Souza"],
        abstract="An overview of deep learning applied to NLP.",
        publication_year=2023,
        doi="10.1000/xyz123",
        url="https://doi.org/10.1000/xyz123",
        external_id="crossref:xyz123",
        metadata={"venue": "ACL"},
    )

    assert result.title == "Deep Learning for NLP"
    assert result.authors == ["Ana Silva", "Bruno Souza"]
    assert result.publication_year == 2023
    assert result.doi == "10.1000/xyz123"
    assert result.metadata == {"venue": "ACL"}


def test_normalized_search_result_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        NormalizedSearchResult(source="openalex", unexpected="value")


def test_two_providers_can_coexist_behind_same_contract() -> None:
    class ProviderA(SearchProvider):
        name = "provider-a"

        def search(self, query: str, options: SearchOptions | None = None) -> list[NormalizedSearchResult]:
            return [NormalizedSearchResult(source=self.name, title=query)]

    class ProviderB(SearchProvider):
        name = "provider-b"

        def search(self, query: str, options: SearchOptions | None = None) -> list[NormalizedSearchResult]:
            return [NormalizedSearchResult(source=self.name, title=query.upper())]

    providers: list[SearchProvider] = [ProviderA(), ProviderB()]
    results = [r for provider in providers for r in provider.search("llm")]

    assert [r.source for r in results] == ["provider-a", "provider-b"]
    assert results[0].title == "llm"
    assert results[1].title == "LLM"
