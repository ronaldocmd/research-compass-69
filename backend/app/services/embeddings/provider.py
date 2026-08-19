"""EmbeddingProvider contract (RDA-023).

Every embedding source (OpenAI, ...) must be adapted behind this
interface so EmbeddingService depends only on this abstraction, never on
a specific provider's SDK. Mirrors the SearchProvider contract (RDA-011).
"""

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Contract implemented by every embedding provider adapter."""

    name: str
    model: str
    dimension: int

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Return the embedding vector for a single piece of text."""
        raise NotImplementedError

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in the same order."""
        raise NotImplementedError
