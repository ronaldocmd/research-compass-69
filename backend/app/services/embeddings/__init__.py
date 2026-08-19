"""Embedding generation service (RDA-023)."""

from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.exceptions import (
    EmbeddingError,
    EmbeddingProviderError,
    EmbeddingProviderInvalidResponseError,
    EmbeddingProviderRateLimitError,
    EmbeddingProviderTimeoutError,
    UnknownEmbeddingProviderError,
)
from app.services.embeddings.openai_provider import OpenAIEmbeddingProvider
from app.services.embeddings.provider import EmbeddingProvider
from app.services.embeddings.schemas import EmbeddingResult

__all__ = [
    "EmbeddingError",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingProviderInvalidResponseError",
    "EmbeddingProviderRateLimitError",
    "EmbeddingProviderTimeoutError",
    "EmbeddingResult",
    "EmbeddingService",
    "OpenAIEmbeddingProvider",
    "UnknownEmbeddingProviderError",
]
