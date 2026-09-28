"""Search abstraction layer (RDA-011 / RDA-012 / RDA-013 / RDA-014 / RDA-016).

Architecture:

    Research (entity) -> SearchService -> SearchProvider -> OpenAlex (RDA-012)
                                        |                 -> Crossref (RDA-013)
                                        |                 -> (other providers)
                                        -> SearchDeduplicator (RDA-016)

Document persistence arrives in a later ticket.
"""

from app.services.search.arxiv import ArxivSearchProvider
from app.services.search.core import CoreSearchProvider
from app.services.search.crossref import CrossrefSearchProvider
from app.services.search.deduplicator import SearchDeduplicator
from app.services.search.europe_pmc import EuropePMCSearchProvider
from app.services.search.openalex import OpenAlexSearchProvider
from app.services.search.provider import SearchProvider
from app.services.search.search_service import SearchService
from app.services.search.semantic_scholar import SemanticScholarSearchProvider
from app.services.search.unpaywall import UnpaywallEnricher

__all__ = [
    "SearchProvider",
    "OpenAlexSearchProvider",
    "CrossrefSearchProvider",
    "SemanticScholarSearchProvider",
    "ArxivSearchProvider",
    "EuropePMCSearchProvider",
    "CoreSearchProvider",
    "UnpaywallEnricher",
    "SearchService",
    "SearchDeduplicator",
]
