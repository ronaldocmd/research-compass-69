"""DocumentRetriever (RDA-024).

    Question (text)
        -> DocumentRetriever
            -> EmbeddingProvider (query embedding, RDA-023)
            -> cosine similarity against an in-memory chunk index
            -> top-K chunks above min_score

For the MVP the index is a plain in-memory list of IndexedChunk entries
(each holding a pre-computed embedding). pgvector can replace this with a
database-backed similarity search later without changing the service
contract.
"""

import math
from datetime import UTC, datetime

from app.core.config import settings
from app.services.embeddings.exceptions import EmbeddingError
from app.services.embeddings.openai_provider import OpenAIEmbeddingProvider
from app.services.embeddings.provider import EmbeddingProvider
from app.services.retrieval.exceptions import RetrievalError
from app.services.retrieval.schemas import IndexedChunk, RetrievedChunk, RetrievalResult


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return the cosine similarity between two vectors.

    Implemented in pure Python (no numpy) so retrieval stays dependency-free
    for the MVP. Vectors of different lengths, empty vectors, or zero-norm
    vectors are treated as having zero similarity rather than raising.
    """
    if len(a) != len(b):
        return 0.0
    if not a:
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(dot / (norm_a * norm_b))


class DocumentRetriever:
    """Finds the chunks most relevant to a question via vector similarity."""

    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        *,
        index: list[IndexedChunk] | None = None,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> None:
        self._provider = provider if provider is not None else OpenAIEmbeddingProvider()
        self._index = list(index) if index is not None else []
        self._top_k = top_k if top_k is not None else settings.RETRIEVAL_TOP_K
        self._min_score = min_score if min_score is not None else settings.RETRIEVAL_MIN_SCORE

    def retrieve(self, query: str, top_k: int | None = None) -> RetrievalResult:
        """Embed ``query`` and return the top-K chunks above ``min_score``.

        Args:
            query: The user's question.
            top_k: Optional per-call override for the number of chunks to
                return. Falls back to the configured RETRIEVAL_TOP_K.

        Returns:
            A RetrievalResult whose chunks are ordered by descending
            similarity. When nothing meets ``min_score`` (or the index is
            empty), the result carries an empty chunk list and
            ``total_found == 0``.

        Raises:
            RetrievalError: When the embedding provider fails to embed the query.
        """
        limit = top_k if top_k is not None else self._top_k

        try:
            query_embedding = self._provider.embed(query)
        except EmbeddingError as exc:
            raise RetrievalError(f"Failed to embed query: {exc}") from exc

        scored = [
            (cosine_similarity(query_embedding, chunk.embedding), chunk)
            for chunk in self._index
        ]

        matches = [
            (score, chunk)
            for score, chunk in scored
            if score >= self._min_score
        ]
        matches.sort(key=lambda item: item[0], reverse=True)

        total_found = len(matches)
        top = matches[:limit]

        chunks = [
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                text=chunk.text,
                page_number=chunk.page_number,
                section=chunk.section,
                score=score,
                document_title=chunk.document_title,
            )
            for score, chunk in top
        ]

        return RetrievalResult(
            query=query,
            chunks=chunks,
            total_found=total_found,
            retrieved_at=datetime.now(UTC),
        )
