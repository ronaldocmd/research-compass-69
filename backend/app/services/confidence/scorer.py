"""ConfidenceScorer (RDA-027).

Computes a deterministic confidence score for a claim from its evidence and,
optionally, the retrieval similarity of its source chunks. No LLM involved.
"""

import uuid
from datetime import UTC, datetime

from app.services.claims.schemas import Claim
from app.services.confidence.rules import (
    average_retrieval,
    base_score,
    classify_level,
    coverage_bonus,
    coverage_label,
    retrieval_bonus,
    retrieval_label,
    strength_label,
    strongest_status,
    supported_count,
)
from app.services.confidence.schemas import ConfidenceLevel, ConfidenceScore, ScoredClaim
from app.services.evidence.schemas import Evidence


class ConfidenceScorer:
    """Assigns a deterministic confidence level to a claim from its evidence."""

    def score(
        self,
        claim: Claim,
        evidence: list[Evidence],
        retrieval_scores: dict[uuid.UUID, float] | None = None,
    ) -> ConfidenceScore:
        """Score ``claim`` against its ``evidence``.

        ``retrieval_scores`` maps chunk_id -> retrieval similarity; it is
        optional and only sharpens the result.
        """
        strength = strongest_status(evidence)
        base = base_score(evidence)
        avg = average_retrieval(claim.chunk_ids, retrieval_scores)
        supported = supported_count(evidence)

        raw = base + retrieval_bonus(avg) + coverage_bonus(supported)
        raw = min(1.0, max(0.0, raw))

        level = classify_level(raw)
        factors = {
            "evidence_strength": strength_label(strength),
            "retrieval_score": retrieval_label(avg),
            "coverage": coverage_label(supported),
        }

        return ConfidenceScore(
            level=level,
            score=round(raw, 4),
            reasoning=self._build_reasoning(level, strength, supported, avg),
            factors=factors,
        )

    def score_claim(
        self,
        claim: Claim,
        evidence: list[Evidence],
        retrieval_scores: dict[uuid.UUID, float] | None = None,
    ) -> ScoredClaim:
        """Score a claim and wrap the result in a ScoredClaim DTO."""
        return ScoredClaim(
            claim=claim,
            evidence=evidence,
            confidence=self.score(claim, evidence, retrieval_scores),
            scored_at=datetime.now(UTC),
        )

    @staticmethod
    def _build_reasoning(
        level: ConfidenceLevel,
        strength: object | None,
        supported: int,
        avg: float | None,
    ) -> str:
        if level == ConfidenceLevel.LOW:
            return (
                "LOW confidence: this claim is not confirmed by the available "
                "evidence and must not be treated as a verified fact."
            )
        head = (
            "HIGH confidence"
            if level == ConfidenceLevel.HIGH
            else "MEDIUM confidence"
        )
        if supported:
            detail = f"based on {supported} supporting evidence item(s)"
        else:
            detail = "based on inconclusive evidence"
        if avg is not None:
            detail += f" and retrieval similarity {avg:.2f}"
        return f"{head}: {detail}."
