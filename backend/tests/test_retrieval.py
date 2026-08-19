"""Tests for DocumentRetriever (RDA-024).

EmbeddingProvider is replaced with a fake in every test: no test performs a
real API call. Chunks are supplied as an in-memory index of IndexedChunk
entries with hand-crafted vectors, so similarity scores are deterministic.
"""

import math
import uuid

import pytest

from app.services.embeddings.exceptions import EmbeddingError
from app.services.embeddings.provider import EmbeddingProvider
from app.services.retrieval.exceptions import RetrievalError
from app.services.retrieval.retriever import DocumentRetriever, cosine_similarity
from app.services.retrieval.schemas import IndexedChunk, RetrievalResult


class _FakeProvider(EmbeddingProvider):
    name = "fake"

    def __init__(self, query_vector: list[float] | None = None) -> None:
        self.model = "fake-model"
        self._query_vector = query_vector or [1.0, 0.0, 0.0]
        self.dimension = len(self._query_vector)
        self.queries: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.queries.append(text)
        return list(self._query_vector)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class _FailingProvider(EmbeddingProvider):
    name = "failing"

    def __init__(self) -> None:
        self.model = "failing"
        self.dimension = 3

    def embed(self, text: str) -> list[float]:
        raise EmbeddingError("simulated provider failure")

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("simulated provider failure")


def _chunk(
    *,
    embedding: list[float],
    text: str = "text",
    document_id: uuid.UUID | None = None,
    chunk_id: uuid.UUID | None = None,
    page_number: int = 1,
    section: str | None = None,
    document_title: str | None = None,
) -> IndexedChunk:
    return IndexedChunk(
        chunk_id=chunk_id or uuid.uuid4(),
        document_id=document_id or uuid.uuid4(),
        text=text,
        page_number=page_number,
        section=section,
        embedding=embedding,
        document_title=document_title,
    )


# --- cosine_similarity -------------------------------------------------------


def test_cosine_similarity_known_values() -> None:
    assert cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine_similarity([1, 1], [1, 1]) == pytest.approx(1.0)
    assert cosine_similarity([1, 1], [1, 0]) == pytest.approx(1 / math.sqrt(2))


def test_cosine_similarity_zero_vector_and_length_mismatch() -> None:
    assert cosine_similarity([0, 0], [1, 0]) == 0.0
    assert cosine_similarity([], [1, 0]) == 0.0
    assert cosine_similarity([1, 0], [1, 0, 0]) == 0.0


# --- DocumentRetriever -------------------------------------------------------


def test_retrieve_returns_chunks_sorted_by_score() -> None:
    provider = _FakeProvider(query_vector=[1.0, 0.0])
    index = [
        _chunk(embedding=[0.0, 1.0], text="perpendicular"),
        _chunk(embedding=[1.0, 0.0], text="exact match"),
        _chunk(embedding=[1.0, 1.0], text="partial match"),
    ]
    retriever = DocumentRetriever(provider=provider, index=index, top_k=5, min_score=0.0)

    result = retriever.retrieve("question")

    assert [c.text for c in result.chunks] == [
        "exact match",
        "partial match",
        "perpendicular",
    ]
    scores = [c.score for c in result.chunks]
    assert scores == sorted(scores, reverse=True)
    assert result.chunks[0].score == pytest.approx(1.0)


def test_retrieve_filters_by_min_score() -> None:
    provider = _FakeProvider(query_vector=[1.0, 0.0])
    index = [
        _chunk(embedding=[1.0, 0.0], text="high"),
        _chunk(embedding=[1.0, 1.0], text="medium"),
        _chunk(embedding=[0.0, 1.0], text="low"),
    ]
    retriever = DocumentRetriever(provider=provider, index=index, top_k=5, min_score=0.8)

    result = retriever.retrieve("question")

    assert [c.text for c in result.chunks] == ["high"]
    assert result.total_found == 1


def test_retrieve_without_matches_returns_empty_list() -> None:
    provider = _FakeProvider(query_vector=[1.0, 0.0])
    index = [_chunk(embedding=[0.0, 1.0])]
    retriever = DocumentRetriever(provider=provider, index=index, top_k=5, min_score=0.7)

    result = retriever.retrieve("question")

    assert result.chunks == []
    assert result.total_found == 0


def test_retrieve_preserves_provenance() -> None:
    provider = _FakeProvider(query_vector=[1.0, 0.0])
    document_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    index = [
        _chunk(
            embedding=[1.0, 0.0],
            chunk_id=chunk_id,
            document_id=document_id,
            page_number=7,
            section="Results",
            document_title="A Study",
            text="the matched text",
        )
    ]
    retriever = DocumentRetriever(provider=provider, index=index, top_k=5, min_score=0.0)

    result = retriever.retrieve("question")

    chunk = result.chunks[0]
    assert chunk.chunk_id == chunk_id
    assert chunk.document_id == document_id
    assert chunk.page_number == 7
    assert chunk.section == "Results"
    assert chunk.document_title == "A Study"
    assert chunk.text == "the matched text"
    assert chunk.score == pytest.approx(1.0)


def test_retrieve_top_k_limits_results_but_total_found_counts_all_matches() -> None:
    provider = _FakeProvider(query_vector=[1.0, 0.0])
    index = [_chunk(embedding=[1.0, 0.0], text=f"c{i}") for i in range(6)]
    retriever = DocumentRetriever(provider=provider, index=index, top_k=3, min_score=0.5)

    result = retriever.retrieve("question")

    assert len(result.chunks) == 3
    assert result.total_found == 6


def test_retrieve_top_k_override_per_call() -> None:
    provider = _FakeProvider(query_vector=[1.0, 0.0])
    index = [_chunk(embedding=[1.0, 0.0], text=f"c{i}") for i in range(5)]
    retriever = DocumentRetriever(provider=provider, index=index, top_k=5, min_score=0.5)

    result = retriever.retrieve("question", top_k=2)

    assert len(result.chunks) == 2


def test_retrieve_embeds_query_with_provider() -> None:
    provider = _FakeProvider(query_vector=[1.0, 0.0])
    retriever = DocumentRetriever(provider=provider, index=[], top_k=5, min_score=0.7)

    retriever.retrieve("what is X?")

    assert provider.queries == ["what is X?"]


def test_retrieve_empty_index_returns_empty_result() -> None:
    provider = _FakeProvider()
    retriever = DocumentRetriever(provider=provider, index=[], top_k=5, min_score=0.7)

    result = retriever.retrieve("question")

    assert isinstance(result, RetrievalResult)
    assert result.query == "question"
    assert result.chunks == []
    assert result.total_found == 0
    assert result.retrieved_at is not None


def test_retrieve_wraps_provider_error_as_retrieval_error() -> None:
    retriever = DocumentRetriever(provider=_FailingProvider(), index=[])

    with pytest.raises(RetrievalError):
        retriever.retrieve("question")


def test_retrieval_config_defaults() -> None:
    from app.core.config import settings

    assert settings.RETRIEVAL_TOP_K == 5
    assert settings.RETRIEVAL_MIN_SCORE == pytest.approx(0.7)
