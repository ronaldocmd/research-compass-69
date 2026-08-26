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


def _l2_norm(vector: list[float]) -> float:
    """Return the L2 norm of ``vector`` (0.0 for empty vectors)."""
    if not vector:
        return 0.0
    return math.sqrt(sum(x * x for x in vector))


def _cosine_with_norms(
    a: list[float], b: list[float], norm_a: float, norm_b: float
) -> float:
    """Cosine similarity using precomputed L2 norms (RDA-054).

    Equivalent to ``cosine_similarity(a, b)`` but avoids recomputing the
    norms, which are stable for immutable chunk embeddings. Vectors of
    different lengths, empty vectors, or zero-norm vectors are treated as
    having zero similarity, matching ``cosine_similarity``.
    """
    if len(a) != len(b):
        return 0.0
    if not a:
        return 0.0
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
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
        # Keep a reference to the caller's index (RDA-054). The production
        # wiring (WorkflowServices) passes a shared, mutable list that the
        # processor appends to as documents are embedded; copying it here
        # would leave the retriever permanently empty. Callers that want an
        # isolated snapshot can pass a copy themselves.
        self._index = index if index is not None else []
        self._top_k = top_k if top_k is not None else settings.RETRIEVAL_TOP_K
        self._min_score = min_score if min_score is not None else settings.RETRIEVAL_MIN_SCORE
        # Precomputed L2 norms of each chunk embedding (RDA-054). Chunk
        # embeddings are immutable once indexed, so their norms are cached
        # and only recomputed for chunks appended after the last sync. This
        # avoids recomputing sqrt(sum(x*x)) for every chunk on every query.
        self._norms: list[float] = []

    def _sync_norms(self) -> None:
        """Extend the cached norms to match the current index length."""
        if len(self._norms) == len(self._index):
            return
        self._norms = [
            _l2_norm(chunk.embedding) for chunk in self._index
        ]

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

        self._sync_norms()
        query_norm = _l2_norm(query_embedding)

        scored = [
            (
                _cosine_with_norms(query_embedding, chunk.embedding, query_norm, chunk_norm),
                chunk,
            )
            for chunk, chunk_norm in zip(self._index, self._norms)
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
