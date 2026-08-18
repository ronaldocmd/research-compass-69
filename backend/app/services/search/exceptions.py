"""Errors shared by every SearchProvider implementation (RDA-012).

Kept provider-agnostic on purpose: concrete adapters (OpenAlex, Crossref,
...) translate their own transport-level failures into these so callers of
SearchProvider never need to know which HTTP client or API is behind it.
"""


class SearchProviderError(Exception):
    """Base class for every error raised by a SearchProvider adapter."""


class SearchProviderTimeoutError(SearchProviderError):
    """The request to the upstream provider timed out."""


class SearchProviderRateLimitError(SearchProviderError):
    """The upstream provider responded with HTTP 429 (rate limited)."""


class SearchProviderHTTPError(SearchProviderError):
    """The upstream provider responded with a non-2xx HTTP status."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class SearchProviderInvalidResponseError(SearchProviderError):
    """The upstream provider returned an unparsable/unexpected payload."""
