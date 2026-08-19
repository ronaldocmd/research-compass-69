"""OpenAI adapter for the EmbeddingProvider contract (RDA-023).

Talks to the OpenAI embeddings API and converts the response into plain
``list[float]`` vectors, so the rest of the system never sees the
OpenAI SDK's response objects. Mirrors the OpenAlex adapter's shape
(app.services.search.openalex).
"""

import openai

from app.core.config import settings
from app.services.embeddings.exceptions import (
    EmbeddingProviderError,
    EmbeddingProviderInvalidResponseError,
    EmbeddingProviderRateLimitError,
    EmbeddingProviderTimeoutError,
)
from app.services.embeddings.provider import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """EmbeddingProvider adapter backed by the OpenAI Embeddings API."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
        client: object | None = None,
    ) -> None:
        self.model = model if model is not None else settings.EMBEDDING_MODEL
        self.dimension = dimension if dimension is not None else settings.EMBEDDING_DIMENSION
        resolved_api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self._client = client or openai.OpenAI(api_key=resolved_api_key)

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client.embeddings.create(model=self.model, input=texts)
        except openai.APITimeoutError as exc:
            raise EmbeddingProviderTimeoutError(str(exc)) from exc
        except openai.RateLimitError as exc:
            raise EmbeddingProviderRateLimitError(str(exc)) from exc
        except openai.APIError as exc:
            raise EmbeddingProviderError(str(exc)) from exc

        try:
            return [item.embedding for item in response.data]
        except (AttributeError, TypeError) as exc:
            raise EmbeddingProviderInvalidResponseError(
                f"Unexpected embeddings response shape: {exc}"
            ) from exc
