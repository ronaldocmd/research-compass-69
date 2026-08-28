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
from app.services.grounding.schemas import GroundingResult, GroundingStatus


class ConfidenceScorer:
    """Assigns a deterministic confidence level to a claim from its evidence."""

    def score(
        self,
        claim: Claim,
        evidence: list[Evidence],
        retrieval_scores: dict[uuid.UUID, float] | None = None,
        grounding_results: list[GroundingResult] | None = None,
    ) -> ConfidenceScore:
        """Score ``claim`` against its ``evidence``.

        ``retrieval_scores`` maps chunk_id -> retrieval similarity; it is
        optional and only sharpens the result.

        ``grounding_results`` (RDA-063) are the deterministic grounding
        outcomes for the claim's evidence. When provided, they gate the score:
        an UNGROUNDED evidence makes SUPPORTED/HIGH impossible, and a
        PARTIALLY_GROUNDED or UNVERIFIABLE evidence caps the level at MEDIUM.
        This prevents retrieval similarity from inflating confidence for
        evidence that is not actually grounded in the source.
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

        # RDA-063: grounding gate. A deterministic grounding failure must not
        # be overridden by a positive retrieval score or extractor status.
        if grounding_results:
            level, raw = self._apply_grounding_gate(level, raw, grounding_results)
            factors["grounding"] = self._grounding_label(grounding_results)

        return ConfidenceScore(
            level=level,
            score=round(raw, 4),
            reasoning=self._build_reasoning(level, strength, supported, avg),
            factors=factors,
        )

    @staticmethod
    def _apply_grounding_gate(
        level: ConfidenceLevel,
        raw: float,
        grounding_results: list[GroundingResult],
    ) -> tuple[ConfidenceLevel, float]:
        """Cap the confidence level/score based on the grounding outcomes.

        - Any UNGROUNDED evidence -> the claim cannot be supported: LOW.
        - Otherwise, if any evidence is PARTIALLY_GROUNDED or UNVERIFIABLE ->
          cap at MEDIUM (qualified, never HIGH).
        """
        statuses = {g.status for g in grounding_results}
        if GroundingStatus.UNGROUNDED in statuses:
            return ConfidenceLevel.LOW, min(raw, 0.2)
        if (
            GroundingStatus.PARTIALLY_GROUNDED in statuses
            or GroundingStatus.UNVERIFIABLE in statuses
        ):
            return ConfidenceLevel.MEDIUM, min(raw, 0.7)
        return level, raw

    @staticmethod
    def _grounding_label(grounding_results: list[GroundingResult]) -> str:
        statuses = {g.status for g in grounding_results}
        if GroundingStatus.UNGROUNDED in statuses:
            return "UNGROUNDED"
        if GroundingStatus.PARTIALLY_GROUNDED in statuses:
            return "PARTIAL"
        if GroundingStatus.UNVERIFIABLE in statuses:
            return "UNVERIFIABLE"
        return "GROUNDED"

    def score_claim(
        self,
        claim: Claim,
        evidence: list[Evidence],
        retrieval_scores: dict[uuid.UUID, float] | None = None,
        grounding_results: list[GroundingResult] | None = None,
    ) -> ScoredClaim:
        """Score a claim and wrap the result in a ScoredClaim DTO."""
        return ScoredClaim(
            claim=claim,
            evidence=evidence,
            confidence=self.score(
                claim, evidence, retrieval_scores, grounding_results
            ),
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
