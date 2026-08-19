"""LLMProvider contract (RDA-025).

Every LLM source (OpenAI, ...) must be adapted behind this interface so the
claim/evidence layers depend only on this abstraction, never on a specific
vendor's SDK. Mirrors the EmbeddingProvider (RDA-023) and SearchProvider
(RDA-011) contracts.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMProvider(ABC):
    """Contract implemented by every LLM provider adapter."""

    name: str
    model: str

    @abstractmethod
    def complete(self, prompt: str, response_model: type[BaseModel]) -> BaseModel:
        """Return a validated instance of ``response_model`` for ``prompt``.

        Providers are responsible for structured output: they must parse and
        validate the model's reply into ``response_model`` before returning
        it, raising ``InvalidLLMResponseError`` when that is not possible.
        """
        raise NotImplementedError
