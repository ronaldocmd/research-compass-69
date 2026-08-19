"""Tests for the OpenAI LLMProvider adapter (RDA-025).

The OpenAI SDK client is replaced with a fake object: no test performs a
real API call.
"""

from types import SimpleNamespace

import openai
import pytest
from pydantic import BaseModel

from app.services.llm.exceptions import (
    InvalidLLMResponseError,
    LLMProviderError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
)
from app.services.llm.openai_provider import OpenAILLMProvider


class _ResponseModel(BaseModel):
    text: str


def _fake_client(*, parsed=None, refusal=None, error=None):
    def parse(**kwargs):
        parse.last_call = kwargs
        if error is not None:
            raise error
        message = SimpleNamespace(parsed=parsed, refusal=refusal)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    parse.last_call = None
    completions = SimpleNamespace(parse=parse)
    chat = SimpleNamespace(completions=completions)
    beta = SimpleNamespace(chat=chat)
    return SimpleNamespace(beta=beta)


def test_complete_returns_parsed_model() -> None:
    client = _fake_client(parsed=_ResponseModel(text="hi"))
    provider = OpenAILLMProvider(model="m", client=client)

    result = provider.complete("prompt", _ResponseModel)

    assert result == _ResponseModel(text="hi")


def test_complete_passes_model_messages_and_response_format() -> None:
    client = _fake_client(parsed=_ResponseModel(text="hi"))
    provider = OpenAILLMProvider(model="gpt-4o-mini", client=client)

    provider.complete("my prompt", _ResponseModel)

    call = client.beta.chat.completions.parse.last_call
    assert call["model"] == "gpt-4o-mini"
    assert call["response_format"] is _ResponseModel
    assert call["messages"] == [{"role": "user", "content": "my prompt"}]


def test_complete_timeout_raises_timeout_error() -> None:
    client = _fake_client(error=openai.APITimeoutError(request=object()))
    provider = OpenAILLMProvider(model="m", client=client)

    with pytest.raises(LLMProviderTimeoutError):
        provider.complete("p", _ResponseModel)


def test_complete_rate_limit_raises_rate_limit_error() -> None:
    error = openai.RateLimitError("limited", response=_fake_http_response(429), body=None)
    provider = OpenAILLMProvider(model="m", client=_fake_client(error=error))

    with pytest.raises(LLMProviderRateLimitError):
        provider.complete("p", _ResponseModel)


def test_complete_generic_api_error_raises_provider_error() -> None:
    error = openai.APIError("boom", request=object(), body=None)
    provider = OpenAILLMProvider(model="m", client=_fake_client(error=error))

    with pytest.raises(LLMProviderError):
        provider.complete("p", _ResponseModel)


def test_complete_missing_parsed_raises_invalid_response_error() -> None:
    provider = OpenAILLMProvider(model="m", client=_fake_client(parsed=None))

    with pytest.raises(InvalidLLMResponseError):
        provider.complete("p", _ResponseModel)


def test_complete_refusal_raises_invalid_response_error() -> None:
    provider = OpenAILLMProvider(model="m", client=_fake_client(refusal="no thanks"))

    with pytest.raises(InvalidLLMResponseError):
        provider.complete("p", _ResponseModel)


def test_complete_wrong_type_raises_invalid_response_error() -> None:
    provider = OpenAILLMProvider(model="m", client=_fake_client(parsed=object()))

    with pytest.raises(InvalidLLMResponseError):
        provider.complete("p", _ResponseModel)


def test_complete_malformed_response_raises_invalid_response_error() -> None:
    def parse(**kwargs):
        return SimpleNamespace(choices=[])

    client = _fake_client(parsed=_ResponseModel(text="x"))
    client.beta.chat.completions.parse = parse
    provider = OpenAILLMProvider(model="m", client=client)

    with pytest.raises(InvalidLLMResponseError):
        provider.complete("p", _ResponseModel)


def _fake_http_response(status_code: int):
    import httpx

    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return httpx.Response(status_code, request=request)
