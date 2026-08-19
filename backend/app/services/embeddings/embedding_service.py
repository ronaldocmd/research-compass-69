"""EmbeddingService: orchestrates EmbeddingProvider adapters (RDA-023).

    Chunk (DTO, from app.services.chunking)
        -> EmbeddingService (orchestration, batching, failure isolation)
            -> EmbeddingProvider (abstraction)
                -> OpenAIEmbeddingProvider | ...

The service never talks to an external API itself: it only delegates to
the configured EmbeddingProvider, in batches, and never lets one chunk's
failure lose the rest of the batch — every input chunk always gets exactly
one EmbeddingResult back, successful or not.
"""

from datetime import UTC, datetime

from app.core.config import settings
from app.services.chunking.schemas import Chunk
from app.services.embeddings.exceptions import EmbeddingError
from app.services.embeddings.openai_provider import OpenAIEmbeddingProvider
from app.services.embeddings.provider import EmbeddingProvider
from app.services.embeddings.schemas import EmbeddingResult

DEFAULT_PROVIDER = "openai"


class EmbeddingService:
    """Generates embeddings for chunks, batching requests and isolating failures."""

    _default_provider_classes: dict[str, type[EmbeddingProvider]] = {
        "openai": OpenAIEmbeddingProvider,
    }

    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        *,
        batch_size: int | None = None,
    ) -> None:
        self._provider = provider or self._default_provider_classes[DEFAULT_PROVIDER]()
        self._batch_size = batch_size if batch_size is not None else settings.EMBEDDING_BATCH_SIZE

    def generate_embeddings(self, chunks: list[Chunk]) -> list[EmbeddingResult]:
        """Embed every chunk's text, in batches, without losing failures.

        Chunks are grouped into batches of ``batch_size``. If an entire
        batch fails (e.g. the provider is unreachable), every chunk in
        that batch gets a failed EmbeddingResult instead of raising and
        losing the remaining batches.
        """
        results: list[EmbeddingResult] = []
        for start in range(0, len(chunks), self._batch_size):
            batch = chunks[start : start + self._batch_size]
            results.extend(self._embed_batch(batch))
        return results

    def _embed_batch(self, batch: list[Chunk]) -> list[EmbeddingResult]:
        try:
            vectors = self._provider.embed_batch([chunk.text for chunk in batch])
        except EmbeddingError as exc:
            return [self._failure(chunk, str(exc)) for chunk in batch]

        if len(vectors) != len(batch):
            reason = f"Provider returned {len(vectors)} vectors for {len(batch)} chunks"
            return [self._failure(chunk, reason) for chunk in batch]

        return [self._success(chunk, vector) for chunk, vector in zip(batch, vectors)]

    def _success(self, chunk: Chunk, vector: list[float]) -> EmbeddingResult:
        return EmbeddingResult(
            chunk_id=chunk.chunk_id,
            embedding=vector,
            model=self._provider.model,
            dimension=len(vector),
            embedded_at=datetime.now(UTC),
            success=True,
        )

    def _failure(self, chunk: Chunk, error: str) -> EmbeddingResult:
        return EmbeddingResult(
            chunk_id=chunk.chunk_id,
            success=False,
            error=error,
        )
