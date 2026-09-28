"""Multi-source search (RDA-066): new providers, parallel search_all, Unpaywall.

No test touches the network: providers get an httpx client over MockTransport.
"""

import time

import httpx
import pytest

from app.core.config import settings
from app.schemas.search import NormalizedSearchResult, SearchOptions
from app.services.search import arxiv as arxiv_module
from app.services.search.arxiv import ArxivSearchProvider
from app.services.search.common import is_pdf_url, strip_boolean, to_arxiv_query
from app.services.search.core import CoreSearchProvider
from app.services.search.deduplicator import SearchDeduplicator
from app.services.search.europe_pmc import EuropePMCSearchProvider
from app.services.search.exceptions import (
    SearchProviderError,
    SearchProviderHTTPError,
    SearchProviderInvalidResponseError,
    SearchProviderRateLimitError,
    SearchProviderTimeoutError,
)
from app.services.search.provider import SearchProvider
from app.services.search.search_service import SearchService
from app.services.search.semantic_scholar import SemanticScholarSearchProvider
from app.services.search.unpaywall import UnpaywallEnricher


@pytest.fixture(autouse=True)
def _no_arxiv_waiting(monkeypatch):
    """Keep the arXiv throttle/backoff from slowing the suite down, and
    reset the process-wide circuit breaker (RDA-067) so one test's failures
    never leak into the next."""
    monkeypatch.setattr(settings, "ARXIV_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(settings, "ARXIV_RETRY_DELAY_SECONDS", 0.0)
    arxiv_module._consecutive_failures = 0
    arxiv_module._breaker_open_until = 0.0
    yield
    arxiv_module._consecutive_failures = 0
    arxiv_module._breaker_open_until = 0.0


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _json(payload, status=200):
    return lambda request: httpx.Response(status, json=payload)


# --- query helpers -----------------------------------------------------------


def test_strip_boolean_reduces_query_to_keywords() -> None:
    assert strip_boolean('("rare earth" OR REE) AND Brazil') == "rare earth REE Brazil"
    assert strip_boolean("plain words") == "plain words"


def test_to_arxiv_query_prefixes_terms_and_joins_bare_terms() -> None:
    assert to_arxiv_query('"rare earth" AND Brazil') == 'all:"rare earth" AND all:Brazil'
    assert to_arxiv_query("rare earth") == "all:rare AND all:earth"
    assert to_arxiv_query("a NOT b") == "all:a ANDNOT all:b"
    assert to_arxiv_query("(a OR b) AND c") == "( all:a OR all:b ) AND all:c"


def test_is_pdf_url() -> None:
    assert is_pdf_url("https://arxiv.org/pdf/2101.00001")
    assert is_pdf_url("https://x.org/files/paper.PDF")
    assert is_pdf_url("https://europepmc.org/articles/PMC1?pdf=render")
    assert not is_pdf_url("https://doi.org/10.1001/abc")
    assert not is_pdf_url(None)


# --- Semantic Scholar --------------------------------------------------------


def test_semantic_scholar_normalizes_and_prefers_open_access_pdf() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        seen["key"] = request.headers.get("x-api-key")
        return httpx.Response(200, json={"total": 1, "data": [{
            "paperId": "abc", "title": "Rare earths in Brazil", "abstract": "About REE.",
            "year": 2021, "authors": [{"name": "A. Silva"}], "citationCount": 7,
            "externalIds": {"DOI": "10.1001/ree", "ArXiv": "2101.1"},
            "openAccessPdf": {"url": "https://repo.org/ree.pdf"}, "url": "https://s2/abc",
        }]})

    provider = SemanticScholarSearchProvider(api_key="k", client=_client(handler))
    [result] = provider.search('"rare earth" AND Brazil', SearchOptions(limit=5))

    assert seen["params"]["query"] == "rare earth Brazil"  # boolean stripped
    assert seen["key"] == "k"
    assert result.source == "semantic_scholar"
    assert result.url == "https://repo.org/ree.pdf"
    assert result.doi == "10.1001/ree" and result.publication_year == 2021
    assert result.authors == ["A. Silva"]
    assert result.metadata["cited_by_count"] == 7


def test_semantic_scholar_empty_result_and_bad_payload() -> None:
    assert SemanticScholarSearchProvider(client=_client(_json({"total": 0}))).search("x") == []
    with pytest.raises(SearchProviderInvalidResponseError):
        SemanticScholarSearchProvider(client=_client(_json({"data": "nope"}))).search("x")


# --- arXiv -------------------------------------------------------------------

_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2101.00001v2</id>
    <published>2021-01-04T10:00:00Z</published>
    <title>Recovery of
      rare earth elements</title>
    <summary>  We study REE recovery.  </summary>
    <author><name>Ana Lima</name></author><author><name>Bo Chen</name></author>
    <arxiv:doi>10.5555/ree</arxiv:doi>
    <link href="http://arxiv.org/abs/2101.00001v2" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2101.00001v2" rel="related" type="application/pdf"/>
    <category term="physics.chem-ph"/>
  </entry>
</feed>"""


def test_arxiv_parses_atom_feed_with_direct_pdf_link() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["q"] = request.url.params["search_query"]
        return httpx.Response(200, text=_ATOM)

    [result] = ArxivSearchProvider(client=_client(handler)).search('"rare earth" AND Brazil')

    assert seen["q"] == 'all:"rare earth" AND all:Brazil'
    assert result.source == "arxiv"
    assert result.title == "Recovery of rare earth elements"  # whitespace collapsed
    assert result.abstract == "We study REE recovery."
    assert result.url == "http://arxiv.org/pdf/2101.00001v2"
    assert result.external_id == "2101.00001"  # version stripped
    assert result.publication_year == 2021
    assert result.doi == "10.5555/ree"
    assert result.authors == ["Ana Lima", "Bo Chen"]


def test_arxiv_rejects_xml_with_entity_declarations() -> None:
    evil = '<?xml version="1.0"?><!DOCTYPE feed [<!ENTITY a "aaaa">]><feed>&a;</feed>'
    provider = ArxivSearchProvider(client=_client(lambda r: httpx.Response(200, text=evil)))
    with pytest.raises(SearchProviderInvalidResponseError):
        provider.search("x")


def test_arxiv_invalid_xml() -> None:
    provider = ArxivSearchProvider(client=_client(lambda r: httpx.Response(200, text="<feed>")))
    with pytest.raises(SearchProviderInvalidResponseError):
        provider.search("x")


# --- Europe PMC --------------------------------------------------------------


def test_europe_pmc_prefers_open_access_pdf_and_cleans_markup() -> None:
    payload = {"resultList": {"result": [
        {
            "id": "123", "source": "MED", "pmcid": "PMC999", "doi": "10.1009/env",
            "title": "Soil <i>metals</i>", "authorString": "Souza A, Lima B.", "pubYear": "2019",
            "abstractText": "<h4>Background</h4><p>Toxic   metals.</p>", "isOpenAccess": "Y",
            "citedByCount": 3,
            "fullTextUrlList": {"fullTextUrl": [
                {"documentStyle": "html", "availability": "Open access", "url": "https://h/html"},
                {"documentStyle": "pdf", "availability": "Open access", "url": "https://h/paper.pdf"},
            ]},
        },
        {"id": "456", "source": "PPR", "pmcid": "PMC777", "isOpenAccess": "Y", "title": "T"},
        {"id": "789", "source": "MED", "doi": "10.1009/closed", "title": "Closed", "isOpenAccess": "N"},
    ]}}
    first, second, third = EuropePMCSearchProvider(client=_client(_json(payload))).search("q")

    assert first.url == "https://h/paper.pdf"
    assert first.title == "Soil metals"
    assert first.abstract == "Background Toxic metals."
    assert first.authors == ["Souza A", "Lima B"]
    assert first.publication_year == 2019
    assert first.external_id == "MED:123"
    assert second.url == "https://europepmc.org/articles/PMC777?pdf=render"
    assert third.url == "https://doi.org/10.1009/closed"  # landing page fallback


def test_europe_pmc_missing_result_list() -> None:
    with pytest.raises(SearchProviderInvalidResponseError):
        EuropePMCSearchProvider(client=_client(_json({"nope": 1}))).search("q")


# --- CORE --------------------------------------------------------------------


def test_core_requires_api_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "CORE_API_KEY", None)
    with pytest.raises(SearchProviderError):
        CoreSearchProvider()


def test_core_normalizes_and_sends_bearer_token() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json={"results": [
            {"id": 55, "title": "Repo paper", "abstract": "A.", "yearPublished": 2020,
             "doi": "10.1007/core", "downloadUrl": "https://core.ac.uk/download/55.pdf",
             "authors": [{"name": "X Y"}]},
            {"id": 56, "title": "Linked", "links": [{"type": "download", "url": "https://l/d.pdf"}]},
        ]})

    first, second = CoreSearchProvider(api_key="secret", client=_client(handler)).search("q")

    assert seen["auth"] == "Bearer secret"
    assert first.url == "https://core.ac.uk/download/55.pdf" and first.external_id == "55"
    assert second.url == "https://l/d.pdf"


# --- shared error mapping ----------------------------------------------------


@pytest.mark.parametrize(
    "status, error",
    [(429, SearchProviderRateLimitError), (503, SearchProviderHTTPError)],
)
def test_new_providers_map_http_errors(status, error) -> None:
    provider = EuropePMCSearchProvider(client=_client(lambda r: httpx.Response(status)))
    with pytest.raises(error):
        provider.search("q")


def test_new_providers_map_timeouts() -> None:
    def handler(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(SearchProviderTimeoutError):
        ArxivSearchProvider(client=_client(handler)).search("q")


# --- dedupe: prefer a direct PDF link ----------------------------------------


def _r(source, url, doi="10.1001/same") -> NormalizedSearchResult:
    return NormalizedSearchResult(source=source, title="Same Paper", doi=doi, url=url)


def test_merge_prefers_pdf_url_over_landing_page() -> None:
    merged = SearchDeduplicator().deduplicate([
        _r("openalex", "https://doi.org/10.1001/same"),
        _r("arxiv", "https://arxiv.org/pdf/2101.00001"),
    ])

    assert len(merged) == 1
    assert merged[0].source == "openalex"  # preferred provider keeps its metadata
    assert merged[0].url == "https://arxiv.org/pdf/2101.00001"


def test_merge_keeps_primary_pdf_when_both_are_pdfs() -> None:
    merged = SearchDeduplicator().deduplicate([
        _r("openalex", "https://a.org/one.pdf"),
        _r("core", "https://b.org/two.pdf"),
    ])
    assert merged[0].url == "https://a.org/one.pdf"


# --- SearchService.search_all ------------------------------------------------


class _Fake(SearchProvider):
    def __init__(self, name, results=None, error=None, delay=0.0) -> None:
        self.name, self._results, self._error, self._delay = name, results or [], error, delay

    def search(self, query, options=None):
        if self._delay:
            time.sleep(self._delay)
        if self._error:
            raise self._error
        return self._results


def _res(source, title, doi=None, url=None) -> NormalizedSearchResult:
    return NormalizedSearchResult(source=source, title=title, doi=doi, url=url)


def test_search_all_merges_and_dedupes_across_providers() -> None:
    service = SearchService(providers={
        "openalex": _Fake("openalex", [_res("openalex", "A", "10.1001/a"), _res("openalex", "B", "10.1001/b")]),
        "arxiv": _Fake("arxiv", [_res("arxiv", "A again", "10.1001/a"), _res("arxiv", "C", "10.1001/c")]),
    })

    titles = sorted(r.title for r in service.search_all("q"))

    assert titles == ["A", "B", "C"]


def test_search_all_survives_partial_failure() -> None:
    service = SearchService(providers={
        "openalex": _Fake("openalex", error=SearchProviderRateLimitError("429")),
        "arxiv": _Fake("arxiv", [_res("arxiv", "Only one", "10.1001/z")]),
    })

    assert [r.title for r in service.search_all("q")] == ["Only one"]


def test_search_all_raises_when_every_provider_fails() -> None:
    service = SearchService(providers={
        "openalex": _Fake("openalex", error=SearchProviderError("down")),
        "arxiv": _Fake("arxiv", error=RuntimeError("boom")),
    })

    with pytest.raises(SearchProviderError, match="All search providers failed"):
        service.search_all("q")


def test_search_all_treats_empty_but_successful_providers_as_success() -> None:
    service = SearchService(providers={"openalex": _Fake("openalex", []), "arxiv": _Fake("arxiv", [])})
    assert service.search_all("q") == []


def test_search_all_runs_providers_in_parallel() -> None:
    service = SearchService(providers={
        f"p{i}": _Fake(f"p{i}", [_res(f"p{i}", f"T{i}", f"10.1001/{i}")], delay=0.3) for i in range(4)
    })

    started = time.perf_counter()
    results = service.search_all("q")
    elapsed = time.perf_counter() - started

    assert len(results) == 4
    assert elapsed < 0.9  # sequential would be >= 1.2s


def test_search_all_interleaves_sources_round_robin() -> None:
    service = SearchService(providers={
        "openalex": _Fake("openalex", [_res("openalex", f"O{i}", f"10.1001/o{i}") for i in range(3)]),
        "arxiv": _Fake("arxiv", [_res("arxiv", f"X{i}", f"10.1002/x{i}") for i in range(3)]),
    })

    assert [r.title for r in service.search_all("q")] == ["O0", "X0", "O1", "X1", "O2", "X2"]


def test_search_all_no_providers_is_an_error() -> None:
    with pytest.raises(SearchProviderError):
        SearchService(providers={}).search_all("q")


def test_search_all_enricher_failure_never_loses_results() -> None:
    class _Broken:
        def enrich(self, results):
            raise RuntimeError("unpaywall exploded")

    service = SearchService(
        providers={"openalex": _Fake("openalex", [_res("openalex", "A", "10.1001/a")])},
        enricher=_Broken(),
    )

    assert [r.title for r in service.search_all("q")] == ["A"]


def test_default_providers_follow_settings_and_skip_core_without_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "CORE_API_KEY", None)
    monkeypatch.setattr(
        settings, "SEARCH_PROVIDERS", "openalex, ARXIV, core, bogus,europe_pmc"
    )

    service = SearchService()

    assert list(service._providers) == ["openalex", "arxiv", "europe_pmc"]


def test_default_providers_include_core_when_key_is_set(monkeypatch) -> None:
    monkeypatch.setattr(settings, "CORE_API_KEY", "k")
    monkeypatch.setattr(settings, "SEARCH_PROVIDERS", "openalex,core")
    assert list(SearchService()._providers) == ["openalex", "core"]


# --- Unpaywall ---------------------------------------------------------------


def test_unpaywall_fills_pdf_for_doi_landing_pages_only() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"best_oa_location": {"url_for_pdf": "https://oa.org/x.pdf"}})

    results = [
        _res("openalex", "Landing", "10.1001/landing", "https://doi.org/10.1001/landing"),
        _res("openalex", "Has pdf", "10.1001/haspdf", "https://a.org/p.pdf"),
        _res("openalex", "No doi", None, "https://a.org/nodoi"),
    ]

    enriched = UnpaywallEnricher(email="me@x.org", client=_client(handler)).enrich(results)

    assert calls == ["/v2/10.1001/landing"]
    assert enriched[0].url == "https://oa.org/x.pdf"
    assert enriched[0].metadata["oa_source"] == "unpaywall"
    assert enriched[1].url == "https://a.org/p.pdf"
    assert enriched[2].url == "https://a.org/nodoi"


def test_unpaywall_is_noop_without_email_and_ignores_lookup_errors() -> None:
    results = [_res("openalex", "A", "10.1001/a", "https://doi.org/10.1001/a")]

    assert UnpaywallEnricher(email=None).enrich(results) == results

    for status in (404, 429, 500):
        enricher = UnpaywallEnricher(email="me@x.org", client=_client(lambda r, s=status: httpx.Response(s)))
        assert enricher.enrich(results)[0].url == "https://doi.org/10.1001/a"

    no_location = UnpaywallEnricher(email="me@x.org", client=_client(_json({"best_oa_location": None})))
    assert no_location.enrich(results)[0].url == "https://doi.org/10.1001/a"


# --- regressions found against the real APIs ---------------------------------


def test_core_calls_trailing_slash_endpoint() -> None:
    """CORE 301-redirects /search/works to /search/works/ (found in live test)."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"results": []})

    CoreSearchProvider(api_key="k", client=_client(handler)).search("q")

    assert seen["path"] == "/v3/search/works/"


def test_providers_follow_http_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "https://x.test/new"})
        return httpx.Response(200, json={"ok": True})

    from app.services.search.common import get_response

    response = get_response("T", "https://x.test/old", timeout=5, client=_client(handler))

    assert response.json() == {"ok": True}


def test_unpaywall_falls_back_to_other_locations_with_a_pdf() -> None:
    payload = {
        "best_oa_location": {"url_for_pdf": None, "url_for_landing_page": "https://doi.org/x"},
        "oa_locations": [
            {"url_for_pdf": None},
            {"url_for_pdf": "https://repo.edu/copy.pdf"},
        ],
    }
    enricher = UnpaywallEnricher(email="me@x.org", client=_client(_json(payload)))

    [result] = enricher.enrich([_res("openalex", "A", "10.1001/a", "https://doi.org/10.1001/a")])

    assert result.url == "https://repo.edu/copy.pdf"


# --- arXiv throttling / 406 seen in production -------------------------------


def test_arxiv_retries_once_when_a_burst_is_refused_with_406() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(406) if len(calls) == 1 else httpx.Response(200, text=_ATOM)

    results = ArxivSearchProvider(client=_client(handler)).search("q")

    assert len(calls) == 2
    assert len(results) == 1


def test_arxiv_gives_up_after_second_refusal_and_does_not_retry_other_errors() -> None:
    always_406 = []
    provider = ArxivSearchProvider(client=_client(lambda r: always_406.append(1) or httpx.Response(406)))
    with pytest.raises(SearchProviderHTTPError):
        provider.search("q")
    assert len(always_406) == 2

    not_found = []
    provider = ArxivSearchProvider(client=_client(lambda r: not_found.append(1) or httpx.Response(404)))
    with pytest.raises(SearchProviderHTTPError):
        provider.search("q")
    assert len(not_found) == 1


def test_arxiv_circuit_breaker_opens_after_threshold_failures(monkeypatch) -> None:
    """RDA-067: repeatedly hammering a refusing arXiv (seen in production:
    every one of a research's ~8 queries kept hitting it, silently
    contributing zero results for the whole run) must stop after a few
    failures instead of retrying forever with no visibility."""
    monkeypatch.setattr(settings, "ARXIV_BREAKER_FAILURE_THRESHOLD", 2)
    monkeypatch.setattr(settings, "ARXIV_BREAKER_COOLDOWN_SECONDS", 60.0)
    calls = []
    provider = ArxivSearchProvider(
        client=_client(lambda r: calls.append(1) or httpx.Response(406))
    )

    # Two failing .search() calls (each retries once internally -> 4 HTTP
    # attempts) reach the threshold and open the breaker.
    for _ in range(2):
        with pytest.raises(SearchProviderHTTPError):
            provider.search("q")
    assert len(calls) == 4

    # The breaker is now open: no HTTP request is attempted at all.
    with pytest.raises(SearchProviderError, match="circuit breaker"):
        provider.search("q")
    assert len(calls) == 4


def test_arxiv_circuit_breaker_closes_after_cooldown_and_a_success(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ARXIV_BREAKER_FAILURE_THRESHOLD", 1)
    monkeypatch.setattr(settings, "ARXIV_BREAKER_COOLDOWN_SECONDS", 0.05)
    provider = ArxivSearchProvider(client=_client(lambda r: httpx.Response(406)))
    with pytest.raises(SearchProviderHTTPError):
        provider.search("q")
    with pytest.raises(SearchProviderError, match="circuit breaker"):
        provider.search("q")

    time.sleep(0.06)
    ok_provider = ArxivSearchProvider(client=_client(lambda r: httpx.Response(200, text=_ATOM)))
    results = ok_provider.search("q")  # succeeds -> breaker closes again
    assert len(results) == 1


def test_arxiv_circuit_breaker_resets_failure_count_on_success(monkeypatch) -> None:
    """A success between failures must not let two unrelated failures,
    separated by a working request, add up toward the threshold."""
    monkeypatch.setattr(settings, "ARXIV_BREAKER_FAILURE_THRESHOLD", 2)
    fail = ArxivSearchProvider(client=_client(lambda r: httpx.Response(406)))
    ok = ArxivSearchProvider(client=_client(lambda r: httpx.Response(200, text=_ATOM)))

    with pytest.raises(SearchProviderHTTPError):
        fail.search("q")
    ok.search("q")  # resets the consecutive-failure count
    with pytest.raises(SearchProviderHTTPError):
        fail.search("q")

    # Still below threshold (2 non-consecutive failures) -> breaker stays closed.
    ok.search("q")


def test_arxiv_requests_are_spaced_process_wide(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ARXIV_MIN_INTERVAL_SECONDS", 0.2)
    provider = ArxivSearchProvider(client=_client(lambda r: httpx.Response(200, text=_ATOM)))
    provider.search("warm up")

    started = time.perf_counter()
    provider.search("a")
    ArxivSearchProvider(client=_client(lambda r: httpx.Response(200, text=_ATOM))).search("b")

    assert time.perf_counter() - started >= 0.38
