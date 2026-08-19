"""Tests for the OpenAI EmbeddingProvider adapter (RDA-023).

The OpenAI SDK client is replaced with a fake object: no test performs a
real API call.
"""

from dataclasses import dataclass

import openai
import pytest

from app.services.embeddings.exceptions import (
    EmbeddingProviderError,
    EmbeddingProviderInvalidResponseError,
    EmbeddingProviderRateLimitError,
    EmbeddingProviderTimeoutError,
)
from app.services.embeddings.openai_provider import OpenAIEmbeddingProvider


@dataclass
class _FakeEmbeddingItem:
    embedding: list[float]


class _FakeEmbeddingsResponse:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.data = [_FakeEmbeddingItem(embedding=vector) for vector in vectors]


class _FakeEmbeddingsEndpoint:
    def __init__(self, *, vectors=None, error: Exception | None = None) -> None:
        self._vectors = vectors
        self._error = error
        self.last_call: dict | None = None

    def create(self, *, model: str, input: list[str]):
        self.last_call = {"model": model, "input": input}
        if self._error is not None:
            raise self._error
        return _FakeEmbeddingsResponse(self._vectors)


class _FakeOpenAIClient:
    def __init__(self, *, vectors=None, error: Exception | None = None) -> None:
        self.embeddings = _FakeEmbeddingsEndpoint(vectors=vectors, error=error)


def _make_provider(*, vectors=None, error: Exception | None = None, dimension: int = 3) -> OpenAIEmbeddingProvider:
    client = _FakeOpenAIClient(vectors=vectors, error=error)
    return OpenAIEmbeddingProvider(model="text-embedding-3-small", dimension=dimension, client=client)


def test_embed_returns_single_vector() -> None:
    provider = _make_provider(vectors=[[0.1, 0.2, 0.3]])

    vector = provider.embed("hello world")

    assert vector == [0.1, 0.2, 0.3]
    assert provider._client.embeddings.last_call == {"model": "text-embedding-3-small", "input": ["hello world"]}


def test_embed_batch_returns_vectors_in_order() -> None:
    provider = _make_provider(vectors=[[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])

    vectors = provider.embed_batch(["a", "b", "c"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]


def test_embed_batch_empty_input_returns_empty_list() -> None:
    provider = _make_provider(vectors=[])

    assert provider.embed_batch([]) == []


def test_embed_batch_timeout_raises_embedding_provider_timeout_error() -> None:
    provider = _make_provider(error=openai.APITimeoutError(request=object()))

    with pytest.raises(EmbeddingProviderTimeoutError):
        provider.embed_batch(["text"])


def test_embed_batch_rate_limit_raises_embedding_provider_rate_limit_error() -> None:
    error = openai.RateLimitError("rate limited", response=_fake_http_response(429), body=None)

    provider = _make_provider(error=error)

    with pytest.raises(EmbeddingProviderRateLimitError):
        provider.embed_batch(["text"])


def test_embed_batch_generic_api_error_raises_embedding_provider_error() -> None:
    provider = _make_provider(error=openai.APIError("boom", request=object(), body=None))

    with pytest.raises(EmbeddingProviderError):
        provider.embed_batch(["text"])


def test_embed_batch_malformed_response_raises_invalid_response_error() -> None:
    client = _FakeOpenAIClient()
    client.embeddings.create = lambda **kwargs: object()
    provider = OpenAIEmbeddingProvider(model="m", dimension=3, client=client)

    with pytest.raises(EmbeddingProviderInvalidResponseError):
        provider.embed_batch(["text"])


def _fake_http_response(status_code: int):
    import httpx

    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    return httpx.Response(status_code, request=request)
