"""Search abstraction layer (RDA-011 / RDA-012).

Architecture:

    Search Service -> SearchProvider -> OpenAlex (RDA-012)
                                      -> Crossref (RDA-013)
                                      -> (other providers)

The orchestrating Search Service, deduplication and document processing
arrive in later tickets.
"""

from app.services.search.openalex import OpenAlexSearchProvider
from app.services.search.provider import SearchProvider

__all__ = ["SearchProvider", "OpenAlexSearchProvider"]
