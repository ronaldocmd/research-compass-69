"""Search abstraction layer (RDA-011).

Future architecture:

    Search Service -> SearchProvider -> OpenAlex
                                      -> Crossref
                                      -> (other providers)

Only the contract lives here for now: concrete providers (OpenAlex,
Crossref, ...) and the orchestrating Search Service arrive in later
tickets. Deduplication and document processing are out of scope too.
"""

from app.services.search.provider import SearchProvider

__all__ = ["SearchProvider"]
