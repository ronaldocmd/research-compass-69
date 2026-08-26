"""Deterministic evidence-quality evaluation (RDA-048)."""

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from app.services.evidence.schemas import Evidence, EvidenceStatus


class EvidenceEvaluation(BaseModel):
    """Metrics for one collection of evidence items."""

    model_config = ConfigDict(extra="forbid")

    total_evidence: int = Field(ge=0)
    grounded_evidence: int = Field(ge=0)
    unsupported_evidence: int = Field(ge=0)
    complete_provenance: int = Field(ge=0)
    grounding_rate: float = Field(ge=0, le=1)
    provenance_rate: float = Field(ge=0, le=1)
    passed: bool


class EvidenceEvaluator:
    """Score evidence without changing or enriching source data."""

    def __init__(self, *, min_grounding_rate: float = 0.8) -> None:
        if not 0 <= min_grounding_rate <= 1:
            raise ValueError("min_grounding_rate must be between 0 and 1")
        self.min_grounding_rate = min_grounding_rate

    def evaluate(self, evidence: Iterable[Evidence]) -> EvidenceEvaluation:
        """Calculate grounding and provenance metrics for evidence items."""
        items = list(evidence)
        grounded = sum(
            item.status == EvidenceStatus.SUPPORTED and bool(item.text)
            for item in items
        )
        unsupported = sum(item.status != EvidenceStatus.SUPPORTED for item in items)
        complete = sum(
            item.document_id is not None
            and item.chunk_id is not None
            and item.page_number is not None
            for item in items
        )
        total = len(items)
        grounding_rate = grounded / total if total else 0.0
        provenance_rate = complete / total if total else 0.0
        return EvidenceEvaluation(
            total_evidence=total,
            grounded_evidence=grounded,
            unsupported_evidence=unsupported,
            complete_provenance=complete,
            grounding_rate=grounding_rate,
            provenance_rate=provenance_rate,
            passed=bool(items)
            and grounding_rate >= self.min_grounding_rate
            and provenance_rate == 1.0,
        )


def evaluate_evidence(
    evidence: Iterable[Evidence], *, min_grounding_rate: float = 0.8
) -> EvidenceEvaluation:
    """Convenience wrapper for evaluating an evidence collection."""
    return EvidenceEvaluator(min_grounding_rate=min_grounding_rate).evaluate(evidence)