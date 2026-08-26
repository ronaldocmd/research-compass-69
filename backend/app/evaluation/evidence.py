"""Objective evidence evaluation for one research execution (RDA-048)."""

import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.services.claims.schemas import Claim
from app.services.evidence.schemas import Evidence


class ClaimEvidenceStatus(BaseModel):
    """Objective evidence and provenance status for one claim."""

    model_config = ConfigDict(extra="forbid")

    claim_id: uuid.UUID
    claim_text: str
    has_evidence: bool
    evidence_count: int = Field(ge=0)
    has_grounding: bool
    provenance_complete: bool


class EvidenceEvaluationResult(BaseModel):
    """Machine-readable evidence coverage report for one research."""

    model_config = ConfigDict(extra="forbid")

    research_id: uuid.UUID
    total_claims: int = Field(ge=0)
    claims_with_evidence: int = Field(ge=0)
    claims_with_evidence_pct: float = Field(ge=0, le=100)
    grounding_rate: float = Field(ge=0, le=100)
    provenance_completeness: float = Field(ge=0, le=100)
    unsupported_claims: list[ClaimEvidenceStatus]


class EvidenceEvaluator:
    """Evaluate presence and traceability without changing source results."""

    def __init__(
        self,
        claim_loader: Callable[[uuid.UUID], Iterable[Claim]] | None = None,
        evidence_loader: Callable[[uuid.UUID], Iterable[Evidence]] | None = None,
    ) -> None:
        self.claim_loader = claim_loader
        self.evidence_loader = evidence_loader

    def evaluate(self, research_id: uuid.UUID) -> EvidenceEvaluationResult:
        """Evaluate claims and evidence loaded for ``research_id``."""
        if self.claim_loader is None or self.evidence_loader is None:
            raise ValueError(
                "EvidenceEvaluator requires claim_loader and evidence_loader"
            )
        claims = list(self.claim_loader(research_id))
        evidence = list(self.evidence_loader(research_id))
        evidence_by_claim: dict[uuid.UUID, list[Evidence]] = {}
        for item in evidence:
            evidence_by_claim.setdefault(item.claim_id, []).append(item)

        statuses = [
            self.claim_status(claim, evidence_by_claim.get(claim.claim_id, []))
            for claim in claims
        ]
        supported = sum(status.has_evidence for status in statuses)
        grounded = sum(status.has_grounding for status in statuses)
        complete = sum(self.check_provenance(item) for item in evidence)
        total = len(claims)
        evidence_total = len(evidence)
        return EvidenceEvaluationResult(
            research_id=research_id,
            total_claims=total,
            claims_with_evidence=supported,
            claims_with_evidence_pct=(supported / total * 100) if total else 0.0,
            grounding_rate=(grounded / total * 100) if total else 0.0,
            provenance_completeness=(complete / evidence_total * 100)
            if evidence_total
            else 0.0,
            unsupported_claims=[status for status in statuses if not status.has_evidence],
        )

    @classmethod
    def claim_status(
        cls, claim: Claim, evidence: Iterable[Evidence]
    ) -> ClaimEvidenceStatus:
        """Return objective coverage for one claim."""
        items = list(evidence)
        has_evidence = bool(items)
        has_grounding = has_evidence and all(
            item.document_id is not None for item in items
        )
        provenance_complete = has_evidence and all(
            cls.check_provenance(item) for item in items
        )
        return ClaimEvidenceStatus(
            claim_id=claim.claim_id,
            claim_text=claim.text,
            has_evidence=has_evidence,
            evidence_count=len(items),
            has_grounding=has_grounding,
            provenance_complete=provenance_complete,
        )

    @staticmethod
    def check_provenance(evidence: Evidence) -> bool:
        """Check provenance fields available in the current Evidence DTO."""
        required = (
            evidence.chunk_id is not None
            and evidence.document_id is not None
            and evidence.page_number is not None
        )
        section = getattr(evidence, "section", None)
        return required and (not hasattr(evidence, "section") or bool(section))


def evaluate_evidence(
    research_id: uuid.UUID,
    claim_loader: Callable[[uuid.UUID], Iterable[Claim]],
    evidence_loader: Callable[[uuid.UUID], Iterable[Evidence]],
) -> EvidenceEvaluationResult:
    """Convenience wrapper for a research-scoped evaluation."""
    return EvidenceEvaluator(claim_loader, evidence_loader).evaluate(research_id)


def write_evaluation_report(
    result: EvidenceEvaluationResult,
    output_dir: str | Path = "data/evaluation",
) -> Path:
    """Write one timestamped JSON report and return its path."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"evidence_v1.0_{timestamp}.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path
