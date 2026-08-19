"""DTOs for evidence validation (RDA-028)."""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class ValidationStatus(str, Enum):
    """Outcome of validating a claim against a piece of evidence."""

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"


class ValidationDraft(BaseModel):
    """What the LLM returns for a single claim/evidence pair."""

    model_config = ConfigDict(extra="forbid")

    status: ValidationStatus
    reasoning: str


class ValidationResult(BaseModel):
    """The recorded outcome of validating a claim against its evidence."""

    model_config = ConfigDict(extra="forbid")

    validation_id: uuid.UUID
    claim_id: uuid.UUID
    evidence_id: uuid.UUID
    status: ValidationStatus
    reasoning: str
    validated_at: datetime
    model_used: str
