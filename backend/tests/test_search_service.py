"""Tests for SearchService orchestration (RDA-014 / RDA-016).

Uses fake SearchProvider implementations injected into SearchService: no
test depends on the real OpenAlex/Crossref APIs.
"""

import pytest

from app.schemas.search import NormalizedSearchResult, SearchOptions
from app.services.search.exceptions import (
    SearchProviderError,
    SearchProviderHTTPError,
    UnknownSearchProviderError,
)
from app.services.search.provider import SearchProvider
from app.services.search.search_service import DEFAULT_PROVIDER, SearchService


class FakeProvider(SearchProvider):
    def __init__(self, name: str, results=None, error: Exception | None = None) -> None:
        self.name = name
        self._results = results or []
        self._error = error
        self.received_query: str | None = None
        self.received_options: SearchOptions | None = None

    def search(self, query: str, options: SearchOptions | None = None) -> list[NormalizedSearchResult]:
        self.received_query = query
        self.received_options = options
        if self._error is not None:
            raise self._error
        return self._results


def test_default_provider_constant_is_openalex() -> None:
    assert DEFAULT_PROVIDER == "openalex"


def test_search_service_registers_openalex_and_crossref_by_default() -> None:
    service = SearchService()

    assert "openalex" in service._providers
    assert "crossref" in service._providers


def test_search_uses_openalex_by_default() -> None:
    fake_openalex = FakeProvider("openalex", results=[NormalizedSearchResult(source="openalex")])
    fake_crossref = FakeProvider("crossref", results=[NormalizedSearchResult(source="crossref")])
    service = SearchService(providers={"openalex": fake_openalex, "crossref": fake_crossref})

    results = service.search("machine learning")

    assert results == [NormalizedSearchResult(source="openalex")]
    assert fake_openalex.received_query == "machine learning"
    assert fake_crossref.received_query is None


def test_search_can_select_crossref_explicitly() -> None:
    fake_openalex = FakeProvider("openalex", results=[NormalizedSearchResult(source="openalex")])
    fake_crossref = FakeProvider("crossref", results=[NormalizedSearchResult(source="crossref")])
    service = SearchService(providers={"openalex": fake_openalex, "crossref": fake_crossref})

    results = service.search("deep learning", provider="crossref")

    assert results == [NormalizedSearchResult(source="crossref")]
    assert fake_crossref.received_query == "deep learning"


def test_search_forwards_options_to_the_selected_provider() -> None:
    fake_openalex = FakeProvider("openalex", results=[])
    service = SearchService(providers={"openalex": fake_openalex})
    options = SearchOptions(limit=5, offset=10)

    service.search("query", options=options)

    assert fake_openalex.received_options is options


def test_search_returns_normalized_results_list() -> None:
    expected = [
        NormalizedSearchResult(source="openalex", title="A"),
        NormalizedSearchResult(source="openalex", title="B"),
    ]
    fake_openalex = FakeProvider("openalex", results=expected)
    service = SearchService(providers={"openalex": fake_openalex})

    results = service.search("query")

    assert results == expected


def test_search_returns_empty_list_when_provider_has_no_results() -> None:
    fake_openalex = FakeProvider("openalex", results=[])
    service = SearchService(providers={"openalex": fake_openalex})

    assert service.search("query") == []


def test_search_raises_unknown_provider_error_for_unregistered_name() -> None:
    service = SearchService(providers={"openalex": FakeProvider("openalex")})

    with pytest.raises(UnknownSearchProviderError) as exc_info:
        service.search("query", provider="scopus")
    assert exc_info.value.provider == "scopus"


def test_unknown_provider_error_is_a_search_provider_error() -> None:
    service = SearchService(providers={"openalex": FakeProvider("openalex")})

    with pytest.raises(SearchProviderError):
        service.search("query", provider="scopus")


def test_search_propagates_search_provider_errors_from_the_provider() -> None:
    failing_provider = FakeProvider(
        "openalex", error=SearchProviderHTTPError(500, "OpenAlex returned HTTP 500")
    )
    service = SearchService(providers={"openalex": failing_provider})

    with pytest.raises(SearchProviderHTTPError) as exc_info:
        service.search("query")
    assert exc_info.value.status_code == 500


def test_search_wraps_unexpected_provider_exceptions_without_leaking_internals() -> None:
    failing_provider = FakeProvider("openalex", error=ValueError("some internal detail"))
    service = SearchService(providers={"openalex": failing_provider})

    with pytest.raises(SearchProviderError) as exc_info:
        service.search("query")
    assert "some internal detail" not in str(exc_info.value)
    assert "openalex" in str(exc_info.value)


def test_search_service_does_not_couple_research_to_providers() -> None:
    # SearchService.search only needs a query string; it has no dependency
    # on the Research model/entity at all.
    import inspect

    from app.services.search.search_service import SearchService as ServiceClass

    signature = inspect.signature(ServiceClass.search)
    assert "research" not in signature.parameters


def test_search_deduplicates_results_by_default() -> None:
    duplicated = [
        NormalizedSearchResult(source="openalex", doi="10.1000/xyz123", title="A"),
        NormalizedSearchResult(source="openalex", doi="10.1000/xyz123", title="A duplicate"),
    ]
    fake_openalex = FakeProvider("openalex", results=duplicated)
    service = SearchService(providers={"openalex": fake_openalex})

    results = service.search("query")

    assert len(results) == 1


def test_search_can_disable_deduplication() -> None:
    duplicated = [
        NormalizedSearchResult(source="openalex", doi="10.1000/xyz123", title="A"),
        NormalizedSearchResult(source="openalex", doi="10.1000/xyz123", title="A duplicate"),
    ]
    fake_openalex = FakeProvider("openalex", results=duplicated)
    service = SearchService(providers={"openalex": fake_openalex})

    results = service.search("query", deduplicate=False)

    assert len(results) == 2


def test_search_service_accepts_custom_provider_preference() -> None:
    openalex_result = NormalizedSearchResult(
        source="openalex", external_id="W1", title="OpenAlex Title"
    )
    crossref_result = NormalizedSearchResult(
        source="crossref", external_id="W1", title="Crossref Title"
    )
    fake_openalex = FakeProvider("openalex", results=[openalex_result])
    fake_crossref = FakeProvider("crossref", results=[crossref_result])
    service = SearchService(
        providers={"openalex": fake_openalex, "crossref": fake_crossref},
        provider_preference=["crossref", "openalex"],
    )

    # Run both providers' results through the same dedup pass manually,
    # mirroring how a future multi-provider search would combine them.
    combined = fake_openalex.search("query") + fake_crossref.search("query")
    deduped = service._deduplicator.deduplicate(combined)

    assert len(deduped) == 1
    assert deduped[0].source == "crossref"
