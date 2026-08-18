"""SearchProvider contract (RDA-011).

Every external search source (OpenAlex, Crossref, ...) must be adapted
behind this interface so the future Search Service depends only on this
abstraction, never on a specific provider's API.
"""

from abc import ABC, abstractmethod

from app.schemas.search import NormalizedSearchResult, SearchOptions


class SearchProvider(ABC):
    """Contract implemented by every search provider adapter."""

    name: str

    @abstractmethod
    def search(
        self,
        query: str,
        options: SearchOptions | None = None,
    ) -> list[NormalizedSearchResult]:
        """Run a search against the provider and return normalized results.

        Implementations own the translation between the provider's native
        request/response shape and the ``NormalizedSearchResult`` contract.
        """
        raise NotImplementedError
