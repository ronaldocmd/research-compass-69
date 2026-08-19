"""Deterministic confidence classification rules (RDA-027).

Pure, data-only rules: no LLM, no I/O. The same inputs always produce the
same output.
"""

from app.services.confidence.schemas import ConfidenceLevel
from app.services.evidence.schemas import Evidence, EvidenceStatus

# Base score contributed by the strongest evidence status. A lone
# ``inconclusive`` evidence must map to MEDIUM (acceptance criteria), hence
# 0.5 here rather than the 0.3 sketched in the ticket.
BASE_SCORE_BY_STATUS: dict[EvidenceStatus, float] = {
    EvidenceStatus.SUPPORTED: 0.6,
    EvidenceStatus.INCONCLUSIVE: 0.5,
    EvidenceStatus.UNSUPPORTED: 0.0,
}

# Retrieval-score bonus thresholds/bonuses.
RETRIEVAL_HIGH_THRESHOLD = 0.85
RETRIEVAL_MEDIUM_THRESHOLD = 0.70
RETRIEVAL_HIGH_BONUS = 0.2
RETRIEVAL_MEDIUM_BONUS = 0.1

# Coverage bonus: multiple supporting evidence items beat a single one.
MULTI_SUPPORTED_MIN = 2
MULTI_SUPPORTED_BONUS = 0.1

# Level thresholds on the continuous score.
HIGH_LEVEL_THRESHOLD = 0.75
MEDIUM_LEVEL_THRESHOLD = 0.45


def strongest_status(evidence: list[Evidence]) -> EvidenceStatus | None:
    """Return the strongest evidence status, or None when the list is empty."""
    if not evidence:
        return None
    statuses = {item.status for item in evidence}
    if EvidenceStatus.SUPPORTED in statuses:
        return EvidenceStatus.SUPPORTED
    if EvidenceStatus.INCONCLUSIVE in statuses:
        return EvidenceStatus.INCONCLUSIVE
    return EvidenceStatus.UNSUPPORTED


def base_score(evidence: list[Evidence]) -> float:
    status = strongest_status(evidence)
    if status is None:
        return 0.0
    return BASE_SCORE_BY_STATUS[status]


def supported_count(evidence: list[Evidence]) -> int:
    """Number of ``supported`` evidence items."""
    return sum(1 for item in evidence if item.status == EvidenceStatus.SUPPORTED)


def average_retrieval(
    chunk_ids: list, retrieval_scores: dict | None
) -> float | None:
    """Average retrieval score over the claim's chunks, or None if unknown."""
    if not retrieval_scores:
        return None
    scores = [retrieval_scores[cid] for cid in chunk_ids if cid in retrieval_scores]
    if not scores:
        return None
    return sum(scores) / len(scores)


def retrieval_bonus(avg: float | None) -> float:
    if avg is None:
        return 0.0
    if avg > RETRIEVAL_HIGH_THRESHOLD:
        return RETRIEVAL_HIGH_BONUS
    if avg > RETRIEVAL_MEDIUM_THRESHOLD:
        return RETRIEVAL_MEDIUM_BONUS
    return 0.0


def coverage_bonus(supported: int) -> float:
    return MULTI_SUPPORTED_BONUS if supported >= MULTI_SUPPORTED_MIN else 0.0


def classify_level(score: float) -> ConfidenceLevel:
    if score >= HIGH_LEVEL_THRESHOLD:
        return ConfidenceLevel.HIGH
    if score >= MEDIUM_LEVEL_THRESHOLD:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


def strength_label(status: EvidenceStatus | None) -> str:
    if status == EvidenceStatus.SUPPORTED:
        return "HIGH"
    if status == EvidenceStatus.INCONCLUSIVE:
        return "MEDIUM"
    return "LOW"


def retrieval_label(avg: float | None) -> str:
    if avg is None:
        return "n/a"
    if avg > RETRIEVAL_HIGH_THRESHOLD:
        return "HIGH"
    if avg > RETRIEVAL_MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def coverage_label(supported: int) -> str:
    if supported >= MULTI_SUPPORTED_MIN:
        return "multiple"
    if supported == 1:
        return "single"
    return "none"
