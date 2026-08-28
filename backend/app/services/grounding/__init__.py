"""Deterministic grounding layer (RDA-063)."""

from app.services.grounding.grounder import evidence_is_grounded, ground
from app.services.grounding.schemas import (
    GroundingResult,
    GroundingStatus,
    NumberMismatch,
)

__all__ = [
    "GroundingResult",
    "GroundingStatus",
    "NumberMismatch",
    "evidence_is_grounded",
    "ground",
]
