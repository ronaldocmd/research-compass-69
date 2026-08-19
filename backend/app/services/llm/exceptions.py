"""Domain exceptions for the LLM layer (RDA-025).

Kept provider-agnostic on purpose, following the same convention as
app.services.embeddings.exceptions and app.services.search.exceptions.
"""


class LLMError(Exception):
    """Base class for every error raised by the LLM layer."""


class LLMProviderError(LLMError):
    """The upstream LLM provider failed to complete a request."""


class LLMProviderTimeoutError(LLMProviderError):
    """The request to the upstream provider timed out."""


class LLMProviderRateLimitError(LLMProviderError):
    """The upstream provider responded with a rate-limit error."""


class InvalidLLMResponseError(LLMError):
    """The provider returned a payload that could not be parsed/validated."""
