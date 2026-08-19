"""DTOs for confidence scoring (RDA-027)."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from app.services.claims.schemas import Claim
from app.services.evidence.schemas import Evidence


class ConfidenceLevel(str, Enum):
    """How reliable a claim is, given its evidence."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ConfidenceScore(BaseModel):
    """A deterministic confidence classification for one claim."""

    model_config = ConfigDict(extra="forbid")

    level: ConfidenceLevel
    score: float  # 0.0 to 1.0, continuous
    reasoning: str  # human-readable explanation
    factors: dict[str, str]  # e.g. {"evidence_strength": "HIGH", ...}


class ScoredClaim(BaseModel):
    """A claim together with its evidence and computed confidence."""

    model_config = ConfigDict(extra="forbid")

    claim: Claim
    evidence: list[Evidence]
    confidence: ConfidenceScore
    scored_at: datetime
