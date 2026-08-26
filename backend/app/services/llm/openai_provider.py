"""OpenAI adapter for the LLMProvider contract (RDA-025).

Uses OpenAI structured outputs (``beta.chat.completions.parse``) so the reply
is validated into the requested Pydantic model before it is returned. Mirrors
the OpenAIEmbeddingProvider adapter (RDA-023): the SDK client is injectable,
so tests can swap in a fake and never perform a real API call.
"""

import uuid

import openai
from pydantic import BaseModel

from app.core.config import settings
from app.services.llm.exceptions import (
    InvalidLLMResponseError,
    LLMProviderError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
)
from app.services.llm.provider import LLMProvider


class OpenAILLMProvider(LLMProvider):
    """LLMProvider adapter backed by the OpenAI Chat Completions API."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: object | None = None,
        usage_tracker: object | None = None,
        research_id: uuid.UUID | None = None,
    ) -> None:
        self.model = model if model is not None else settings.LLM_MODEL
        resolved_api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self._client = client or openai.OpenAI(api_key=resolved_api_key)
        # Optional cost tracking (RDA-050): when a UsageTracker and a
        # research_id are provided, each successful completion is recorded.
        self._usage_tracker = usage_tracker
        self._research_id = research_id

    def complete(self, prompt: str, response_model: type[BaseModel]) -> BaseModel:
        try:
            completion = self._client.beta.chat.completions.parse(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format=response_model,
            )
        except openai.APITimeoutError as exc:
            raise LLMProviderTimeoutError(str(exc)) from exc
        except openai.RateLimitError as exc:
            raise LLMProviderRateLimitError(str(exc)) from exc
        except openai.APIError as exc:
            raise LLMProviderError(str(exc)) from exc

        try:
            message = completion.choices[0].message
        except (AttributeError, IndexError, TypeError) as exc:
            raise InvalidLLMResponseError(
                f"Unexpected chat completion shape: {exc}"
            ) from exc

        if getattr(message, "refusal", None):
            raise InvalidLLMResponseError(
                f"Model refused the request: {message.refusal}"
            )

        parsed = getattr(message, "parsed", None)
        if parsed is None:
            raise InvalidLLMResponseError("Model returned no parsed structured output")

        if not isinstance(parsed, response_model):
            raise InvalidLLMResponseError(
                f"Expected {response_model.__name__}, got {type(parsed).__name__}"
            )

        self._record_usage(completion)
        return parsed

    def _record_usage(self, completion) -> None:
        """Record token usage for this completion when tracking is enabled."""
        if self._usage_tracker is None or self._research_id is None:
            return
        usage = getattr(completion, "usage", None)
        if usage is None:
            return
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        self._usage_tracker.record_llm_call(
            research_id=self._research_id,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
