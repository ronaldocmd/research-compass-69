"""Domain exceptions for claim extraction (RDA-025)."""

from app.services.llm.exceptions import InvalidLLMResponseError


class ClaimExtractionError(Exception):
    """Base class for every error raised by the claim extraction layer."""


__all__ = ["ClaimExtractionError", "InvalidLLMResponseError"]
