"""SearchService: orchestrates SearchProvider adapters (RDA-014 / RDA-016).

    Research (entity)
        -> SearchService (orchestration)
            -> SearchProvider (abstraction)
                -> OpenAlexSearchProvider | CrossrefSearchProvider | ...

The service never talks to an external API itself and never depends on any
provider's native response shape: it only picks a SearchProvider by name and
delegates to it, so Research stays decoupled from concrete providers.
Results are deduplicated (RDA-016) by default before being returned.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings
from app.schemas.search import NormalizedSearchResult, SearchOptions
from app.services.search.arxiv import ArxivSearchProvider
from app.services.search.core import CoreSearchProvider
from app.services.search.europe_pmc import EuropePMCSearchProvider
from app.services.search.semantic_scholar import SemanticScholarSearchProvider
from app.services.search.unpaywall import UnpaywallEnricher
from app.services.search.crossref import CrossrefSearchProvider
from app.services.search.deduplicator import DEFAULT_PROVIDER_PREFERENCE, SearchDeduplicator
from app.services.search.exceptions import SearchProviderError, UnknownSearchProviderError
from app.services.search.openalex import OpenAlexSearchProvider
from app.services.search.provider import SearchProvider

DEFAULT_PROVIDER = "openalex"

logger = logging.getLogger(__name__)


class SearchService:
    """Orchestrates search execution across the registered SearchProvider(s)."""

    _default_provider_classes: dict[str, type[SearchProvider]] = {
        "openalex": OpenAlexSearchProvider,
        "crossref": CrossrefSearchProvider,
        "semantic_scholar": SemanticScholarSearchProvider,
        "arxiv": ArxivSearchProvider,
        "europe_pmc": EuropePMCSearchProvider,
        "core": CoreSearchProvider,
    }

    def __init__(
        self,
        providers: dict[str, SearchProvider] | None = None,
        provider_preference: list[str] | None = None,
        enricher: UnpaywallEnricher | None = None,
    ) -> None:
        self._providers: dict[str, SearchProvider] = (
            providers if providers is not None else self._build_default_providers()
        )
        self._deduplicator = SearchDeduplicator(
            provider_preference=provider_preference or DEFAULT_PROVIDER_PREFERENCE
        )
        # Injected providers (tests, custom setups) are used as given; the
        # default enricher is a no-op unless UNPAYWALL_EMAIL is configured.
        self._enricher = enricher if enricher is not None else (
            UnpaywallEnricher() if providers is None else None
        )

    @classmethod
    def _build_default_providers(cls) -> dict[str, SearchProvider]:
        """Instantiate the providers named in ``SEARCH_PROVIDERS``.

        Unknown names are ignored with a warning; a provider that cannot be
        built (e.g. CORE without an API key) is skipped, not fatal.
        """
        providers: dict[str, SearchProvider] = {}
        for name in settings.search_provider_names:
            provider_cls = cls._default_provider_classes.get(name)
            if provider_cls is None:
                logger.warning("Ignoring unknown search provider %r in SEARCH_PROVIDERS", name)
                continue
            try:
                providers[name] = provider_cls()
            except SearchProviderError as exc:
                logger.info("Search provider %r disabled: %s", name, exc)
        return providers

    def search_all(
        self,
        query: str,
        options: SearchOptions | None = None,
        deduplicate: bool = True,
    ) -> list[NormalizedSearchResult]:
        """Query every registered provider in parallel and merge the results.

        A failing provider is logged and skipped so one outage or rate limit
        does not lose the others; only when *all* providers fail is a
        SearchProviderError raised. Results are deduplicated across
        providers, enriched with open-access PDF links (Unpaywall, when
        configured) and interleaved round-robin by source so that
        downstream selection is not dominated by whichever provider is
        listed first.
        """
        if not self._providers:
            raise SearchProviderError("No search providers are enabled")

        def run(item: tuple[str, SearchProvider]):
            name, provider = item
            try:
                return name, provider.search(query, options), None
            except Exception as exc:  # isolate every provider failure
                return name, [], exc

        with ThreadPoolExecutor(max_workers=len(self._providers)) as pool:
            outcomes = list(pool.map(run, self._providers.items()))

        errors = {name: exc for name, _, exc in outcomes if exc is not None}
        for name, exc in errors.items():
            logger.warning("Search provider %r failed for query %r: %s", name, query, exc)
        if len(errors) == len(outcomes):
            detail = "; ".join(f"{n}: {e}" for n, e in errors.items())
            raise SearchProviderError(f"All search providers failed ({detail})")

        merged = [result for _, results, _ in outcomes for result in results]
        if deduplicate:
            merged = self._deduplicator.deduplicate(merged)
        if self._enricher is not None:
            try:
                merged = self._enricher.enrich(merged)
            except Exception as exc:  # enrichment must never lose results
                logger.warning("Unpaywall enrichment failed: %s", exc)
        return self._interleave(merged)

    @staticmethod
    def _interleave(results: list[NormalizedSearchResult]) -> list[NormalizedSearchResult]:
        """Round-robin results by source, keeping each source's own ranking."""
        by_source: dict[str, list[NormalizedSearchResult]] = {}
        for result in results:
            by_source.setdefault(result.source, []).append(result)
        queues = list(by_source.values())
        out: list[NormalizedSearchResult] = []
        for rank in range(max((len(q) for q in queues), default=0)):
            out.extend(q[rank] for q in queues if rank < len(q))
        return out

    def search(
        self,
        query: str,
        provider: str = DEFAULT_PROVIDER,
        options: SearchOptions | None = None,
        deduplicate: bool = True,
    ) -> list[NormalizedSearchResult]:
        """Execute a search through the selected provider.

        Args:
            query: Search term.
            provider: Registered provider name (e.g. "openalex", "crossref").
            options: Search options (limit, offset, filters).
            deduplicate: Whether to collapse duplicate results before
                returning them (default True; see SearchDeduplicator).

        Returns:
            List of normalized results.

        Raises:
            SearchProviderError: When the provider is unknown or the search fails.
        """
        selected = self._resolve_provider(provider)
        try:
            results = selected.search(query, options)
        except SearchProviderError:
            raise
        except Exception as exc:
            raise SearchProviderError(
                f"Search failed for provider '{provider}'"
            ) from exc

        if deduplicate:
            return self._deduplicator.deduplicate(results)
        return results

    def _resolve_provider(self, provider: str) -> SearchProvider:
        try:
            return self._providers[provider]
        except KeyError as exc:
            raise UnknownSearchProviderError(provider) from exc
