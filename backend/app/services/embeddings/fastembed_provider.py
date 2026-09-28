from app.core.config import settings
from app.services.embeddings.exceptions import EmbeddingError
from app.services.embeddings.provider import EmbeddingProvider

class FastEmbedProvider(EmbeddingProvider):
    """EmbeddingProvider adapter backed by local fastembed models."""

    name = "fastembed"

    def __init__(self, model: str | None = None) -> None:
        self.model = model if model is not None else (settings.EMBEDDING_MODEL or "BAAI/bge-small-en-v1.5")
        try:
            # Imported lazily: fastembed is an optional dependency and must not
            # break app import (or the test suite) when it is not installed.
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model)
        except Exception as e:
            raise EmbeddingError(f"Failed to load fastembed model: {e}") from e

    def embed(self, text: str) -> list[float]:
        try:
            return list(next(self._model.embed([text])))
        except Exception as e:
            raise EmbeddingError(f"Failed to embed text: {e}") from e

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            return [list(embedding) for embedding in self._model.embed(texts)]
        except Exception as e:
            raise EmbeddingError(f"Failed to embed batch: {e}") from e
