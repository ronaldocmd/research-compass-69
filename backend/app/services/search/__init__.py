"""Search abstraction layer (RDA-011 / RDA-012 / RDA-013 / RDA-014 / RDA-016).

Architecture:

    Research (entity) -> SearchService -> SearchProvider -> OpenAlex (RDA-012)
                                        |                 -> Crossref (RDA-013)
                                        |                 -> (other providers)
                                        -> SearchDeduplicator (RDA-016)

Document persistence arrives in a later ticket.
"""

from app.services.search.crossref import CrossrefSearchProvider
from app.services.search.deduplicator import SearchDeduplicator
from app.services.search.openalex import OpenAlexSearchProvider
from app.services.search.provider import SearchProvider
from app.services.search.search_service import SearchService

__all__ = [
    "SearchProvider",
    "OpenAlexSearchProvider",
    "CrossrefSearchProvider",
    "SearchService",
    "SearchDeduplicator",
]
