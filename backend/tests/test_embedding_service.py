"""Tests for EmbeddingService (RDA-023).

EmbeddingProvider is replaced with a fake/mock in every test: no test
performs a real API call.
"""

import uuid

import pytest

from app.services.chunking.schemas import Chunk
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.exceptions import EmbeddingProviderError
from app.services.embeddings.provider import EmbeddingProvider


class _FakeProvider(EmbeddingProvider):
    name = "fake"

    def __init__(self, *, dimension: int = 3, model: str = "fake-model", fail_texts: set[str] | None = None) -> None:
        self.model = model
        self.dimension = dimension
        self._fail_texts = fail_texts or set()
        self.batches: list[list[str]] = []

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        if any(text in self._fail_texts for text in texts):
            raise EmbeddingProviderError("simulated provider failure")
        return [[float(len(text))] * self.dimension for text in texts]


def _make_chunk(text: str, *, index: int = 0) -> Chunk:
    return Chunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        text=text,
        page_number=1,
        section=None,
        index=index,
        char_count=len(text),
    )


def test_generate_embeddings_single_chunk() -> None:
    provider = _FakeProvider(dimension=4)
    service = EmbeddingService(provider=provider, batch_size=10)
    chunk = _make_chunk("hello")

    results = service.generate_embeddings([chunk])

    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert result.chunk_id == chunk.chunk_id
    assert result.embedding == [5.0, 5.0, 5.0, 5.0]
    assert result.model == "fake-model"
    assert result.dimension == 4
    assert result.embedded_at is not None
    assert result.error is None


def test_generate_embeddings_batch_processing_groups_calls() -> None:
    provider = _FakeProvider()
    service = EmbeddingService(provider=provider, batch_size=2)
    chunks = [_make_chunk(f"chunk-{i}", index=i) for i in range(5)]

    results = service.generate_embeddings(chunks)

    assert len(results) == 5
    assert all(result.success for result in results)
    assert len(provider.batches) == 3
    assert [len(batch) for batch in provider.batches] == [2, 2, 1]


def test_generate_embeddings_partial_failure_isolates_failing_batch() -> None:
    provider = _FakeProvider(fail_texts={"bad-chunk"})
    service = EmbeddingService(provider=provider, batch_size=1)
    chunks = [_make_chunk("good-1"), _make_chunk("bad-chunk"), _make_chunk("good-2")]

    results = service.generate_embeddings(chunks)

    assert len(results) == 3
    assert results[0].success is True
    assert results[1].success is False
    assert results[1].error == "simulated provider failure"
    assert results[1].embedding is None
    assert results[2].success is True


def test_generate_embeddings_failure_does_not_drop_other_batches() -> None:
    provider = _FakeProvider(fail_texts={"bad-chunk"})
    service = EmbeddingService(provider=provider, batch_size=2)
    chunks = [_make_chunk("bad-chunk"), _make_chunk("good-1"), _make_chunk("good-2"), _make_chunk("good-3")]

    results = service.generate_embeddings(chunks)

    assert len(results) == 4
    assert results[0].success is False
    assert results[1].success is False
    assert results[2].success is True
    assert results[3].success is True


def test_generate_embeddings_empty_list_returns_empty_result() -> None:
    service = EmbeddingService(provider=_FakeProvider())

    assert service.generate_embeddings([]) == []


def test_generate_embeddings_preserves_chunk_metadata_via_chunk_id() -> None:
    provider = _FakeProvider()
    service = EmbeddingService(provider=provider, batch_size=10)
    chunks = [_make_chunk("a"), _make_chunk("b")]

    results = service.generate_embeddings(chunks)

    assert {r.chunk_id for r in results} == {c.chunk_id for c in chunks}
