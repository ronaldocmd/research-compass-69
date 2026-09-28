"""OpenAI adapter for the LLMProvider contract (RDA-025).

Uses OpenAI structured outputs (``beta.chat.completions.parse``) so the reply
is validated into the requested Pydantic model before it is returned. Mirrors
the OpenAIEmbeddingProvider adapter (RDA-023): the SDK client is injectable,
so tests can swap in a fake and never perform a real API call.
"""

import json
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


def _extract_json_object(content: str) -> str:
    """Return the first balanced ``{...}`` object in ``content``.

    Strips ```json fences and surrounding prose; string literals are honoured
    so braces inside strings do not confuse the scan. Falls back to the
    stripped content so the caller reports the validation error.
    """
    text = content.strip()
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return text[start:]


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
        resolved_api_key = api_key if api_key is not None else (settings.LLM_API_KEY or settings.OPENAI_API_KEY)
        self._client = client or openai.OpenAI(
            api_key=resolved_api_key, base_url=settings.LLM_BASE_URL or None, timeout=settings.LLM_TIMEOUT_SECONDS
        )
        # Optional cost tracking (RDA-050): when a UsageTracker and a
        # research_id are provided, each successful completion is recorded.
        self._usage_tracker = usage_tracker
        self._research_id = research_id

    def complete(self, prompt: str, response_model: type[BaseModel]) -> BaseModel:
        try:
            base_url = settings.LLM_BASE_URL or ""
            if "deepseek" in self.model.lower() or "litellm" in base_url:
                schema_json = json.dumps(response_model.model_json_schema())
                completion = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You MUST reply with a valid JSON object matching the requested schema. Return ONLY valid JSON, no markdown formatting like ```json.",
                        },
                        {
                            "role": "user",
                            "content": (
                                f"{prompt}\n\nYou must return a JSON object that "
                                f"perfectly matches this JSON schema:\n{schema_json}"
                            ),
                        },
                    ],
                    response_format={"type": "json_object"},
                )
                self._attach_parsed(completion, response_model)
            else:
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

    @staticmethod
    def _attach_parsed(completion, response_model: type[BaseModel]) -> None:
        """Parse a plain-JSON completion into ``response_model`` (non-OpenAI models).

        Models without native structured output often wrap the JSON in a
        markdown fence or add prose around it, so the first balanced JSON
        object is extracted before validation.
        """
        try:
            message = completion.choices[0].message
            content = message.content or ""
        except (AttributeError, IndexError, TypeError) as exc:
            raise InvalidLLMResponseError(
                f"Unexpected chat completion shape: {exc}"
            ) from exc
        try:
            message.parsed = response_model.model_validate_json(
                _extract_json_object(content)
            )
        except ValueError as exc:  # pydantic.ValidationError is a ValueError
            raise InvalidLLMResponseError(
                f"Failed to parse JSON: {exc}\nContent: {content[:500]}"
            ) from exc

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

