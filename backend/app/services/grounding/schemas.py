"""DTOs for deterministic grounding (RDA-063).

The grounding layer is the deterministic gate that verifies objectively
verifiable facts before any semantic (LLM) judgment is trusted. It answers
"did this evidence actually come from this source, and are the claim's
verifiable facts consistent with it?" — never "does this evidence support the
claim semantically?" (that is the LLM's job).

Taxonomy (minimal, chosen to represent the observed cases):

    GROUNDED            evidence text is present in the chunk (after safe
                        normalization) and the claim's verifiable facts
                        (numbers, negation) are consistent with the evidence.
    PARTIALLY_GROUNDED  part of the evidence/claim is grounded but not all
                        (e.g. a compound claim only partially covered, or a
                        number mismatch on a secondary fact).
    UNGROUNDED          the evidence text is not present in the chunk, or a
                        verifiable fact (number/negation) directly contradicts
                        the source. A claim cannot be SUPPORTED.
    UNVERIFIABLE        no chunk is available to check against (e.g. evidence
                        without a chunk reference). The result must be
                        qualified, never HIGH.

"Not found textually" is NOT treated as "false": normalization, OCR,
whitespace and legitimate paraphrase can hide a real passage. UNGROUNDED is
only returned when the evidence text is genuinely absent after safe
normalization, or when a verifiable fact is contradicted.
"""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class GroundingStatus(str, Enum):
    """Outcome of the deterministic grounding check."""

    GROUNDED = "grounded"
    PARTIALLY_GROUNDED = "partially_grounded"
    UNGROUNDED = "ungrounded"
    UNVERIFIABLE = "unverifiable"


class NumberMismatch(BaseModel):
    """A numeric fact present in the claim but inconsistent with the source."""

    model_config = ConfigDict(extra="forbid")

    value: str
    source_value: str | None = None
    context: str = ""


class GroundingResult(BaseModel):
    """The deterministic grounding outcome for one claim/evidence pair."""

    model_config = ConfigDict(extra="forbid")

    grounding_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    claim_id: uuid.UUID
    evidence_id: uuid.UUID
    status: GroundingStatus
    evidence_grounded: bool
    number_mismatches: list[NumberMismatch] = Field(default_factory=list)
    negation_flipped: bool = False
    # SHA-256 of the source chunk text at grounding time (RDA-063). Lets the
    # provenance chain detect later tampering of the source content.
    content_hash: str | None = None
    reason: str
    grounded_at: datetime = Field(default_factory=lambda: datetime.now())
