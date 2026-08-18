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

from app.schemas.search import NormalizedSearchResult, SearchOptions
from app.services.search.crossref import CrossrefSearchProvider
from app.services.search.deduplicator import DEFAULT_PROVIDER_PREFERENCE, SearchDeduplicator
from app.services.search.exceptions import SearchProviderError, UnknownSearchProviderError
from app.services.search.openalex import OpenAlexSearchProvider
from app.services.search.provider import SearchProvider

DEFAULT_PROVIDER = "openalex"


class SearchService:
    """Orchestrates search execution across the registered SearchProvider(s)."""

    _default_provider_classes: dict[str, type[SearchProvider]] = {
        "openalex": OpenAlexSearchProvider,
        "crossref": CrossrefSearchProvider,
    }

    def __init__(
        self,
        providers: dict[str, SearchProvider] | None = None,
        provider_preference: list[str] | None = None,
    ) -> None:
        self._providers: dict[str, SearchProvider] = (
            providers
            if providers is not None
            else {name: cls() for name, cls in self._default_provider_classes.items()}
        )
        self._deduplicator = SearchDeduplicator(
            provider_preference=provider_preference or DEFAULT_PROVIDER_PREFERENCE
        )

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
