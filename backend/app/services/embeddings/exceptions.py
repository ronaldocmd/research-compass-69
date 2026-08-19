"""Domain exceptions for embedding generation (RDA-023).

Kept provider-agnostic on purpose, following the same convention as
app.services.search.exceptions: concrete adapters (OpenAI, ...) translate
their own transport-level failures into these so callers of
EmbeddingProvider never need to know which SDK or API is behind it.
"""


class EmbeddingError(Exception):
    """Base class for every error raised by the embeddings layer."""


class EmbeddingProviderError(EmbeddingError):
    """The upstream embedding provider failed to produce an embedding."""


class EmbeddingProviderTimeoutError(EmbeddingProviderError):
    """The request to the upstream provider timed out."""


class EmbeddingProviderRateLimitError(EmbeddingProviderError):
    """The upstream provider responded with a rate-limit error."""


class EmbeddingProviderInvalidResponseError(EmbeddingProviderError):
    """The upstream provider returned an unparsable/unexpected payload."""


class UnknownEmbeddingProviderError(EmbeddingError):
    """EmbeddingService was asked to use a provider name it does not know."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"Unknown embedding provider: {provider!r}")
        self.provider = provider
