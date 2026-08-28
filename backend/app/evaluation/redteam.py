"""RDA-062 red-team evaluation of the epistemological chain decision layer.

The decision layer is the deterministic logic that decides whether a claim
reaches the synthesis summary as a supported finding:

    evidence.status (extractor) + retrieval_scores
        -> ConfidenceScorer.score -> confidence level
        -> synthesis gate (level >= SYNTHESIS_MIN_CONFIDENCE)

This module runs that decision layer against a labelled benchmark of
adversarial claim/evidence cases and reports accuracy, precision, recall,
false-positive rate and false-negative rate. It is fully deterministic and
reproducible: the extractor/validator statuses are supplied by the benchmark
(as a correct system would assign them), isolating the decision logic.

The benchmark also records the independent validation status per case. The
decision layer may optionally consume validation results (the RDA-062 fix);
when it does, a claim whose validation is UNSUPPORTED must not reach the
summary regardless of its confidence score.
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.claims.schemas import Claim
from app.services.confidence.scorer import ConfidenceScorer
from app.services.confidence.schemas import ConfidenceLevel
from app.services.evidence.schemas import Evidence, EvidenceStatus
from app.services.validation.schemas import ValidationStatus

BENCHMARK_PATH = Path(__file__).parents[2] / "data" / "benchmarks" / "redteam_rda062_v1.json"


class RedTeamCase(BaseModel):
    """One labelled adversarial case for the decision layer."""

    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
    claim: str
    evidence: str
    evidence_status: EvidenceStatus
    validation_status: ValidationStatus
    expected_in_summary: bool


class RedTeamDataset(BaseModel):
    """A versioned collection of red-team cases."""

    model_config = ConfigDict(extra="forbid")

    version: str
    created_at: datetime
    description: str | None = None
    cases: list[RedTeamCase] = Field(min_length=1)


class RedTeamMetrics(BaseModel):
    """Aggregate decision-layer metrics over the benchmark."""

    model_config = ConfigDict(extra="forbid")

    total: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    accuracy: float
    precision: float
    recall: float
    false_positive_rate: float
    false_negative_rate: float


class RedTeamResult(BaseModel):
    """Per-case decision outcome plus aggregate metrics."""

    model_config = ConfigDict(extra="forbid")

    version: str
    min_confidence: str
    use_validation: bool
    cases: list[dict[str, Any]]
    metrics: RedTeamMetrics


def load_redteam(path: str | Path = BENCHMARK_PATH) -> RedTeamDataset:
    raw = Path(path).read_text(encoding="utf-8")
    return RedTeamDataset.model_validate(json.loads(raw))


def _claim(text: str) -> Claim:
    return Claim(
        claim_id=uuid.uuid4(),
        text=text,
        chunk_ids=[uuid.uuid4()],
        document_id=uuid.uuid4(),
        page_number=1,
        extracted_at=datetime.now(UTC),
    )


def _evidence(text: str, status: EvidenceStatus) -> Evidence:
    return Evidence(
        evidence_id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        text=text,
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        page_number=1,
        status=status,
        extracted_at=datetime.now(UTC),
    )


def _level_rank(level: ConfidenceLevel) -> int:
    return {ConfidenceLevel.HIGH: 3, ConfidenceLevel.MEDIUM: 2, ConfidenceLevel.LOW: 1}[level]


def _min_level(min_confidence: str) -> ConfidenceLevel:
    try:
        return ConfidenceLevel(min_confidence)
    except ValueError:
        return ConfidenceLevel.MEDIUM


def _validation_blocks(validation_status: ValidationStatus) -> bool:
    """Whether a validation status must keep a claim out of the summary.

    Only a SUPPORTED validation permits a claim to be presented as a finding.
    PARTIALLY_SUPPORTED and UNSUPPORTED both block it (conservative default).
    """
    return validation_status != ValidationStatus.SUPPORTED


def decide(
    case: RedTeamCase,
    *,
    scorer: ConfidenceScorer,
    min_confidence: str,
    use_validation: bool,
    retrieval_score: float = 0.9,
) -> tuple[bool, ConfidenceLevel, float]:
    """Return (in_summary, level, score) for one case under the decision layer.

    ``use_validation`` toggles the RDA-062 fix: when True, a claim whose
    validation is not SUPPORTED is excluded from the summary regardless of its
    confidence score.
    """
    claim = _claim(case.claim)
    evidence = [_evidence(case.evidence, case.evidence_status)]
    chunk_id = claim.chunk_ids[0]
    scored = scorer.score_claim(
        claim, evidence, retrieval_scores={chunk_id: retrieval_score}
    )
    level = scored.confidence.level
    score = scored.confidence.score

    if use_validation and _validation_blocks(case.validation_status):
        return False, level, score

    in_summary = _level_rank(level) >= _level_rank(_min_level(min_confidence))
    return in_summary, level, score


def run_redteam(
    *,
    min_confidence: str = "MEDIUM",
    use_validation: bool = False,
    retrieval_score: float = 0.9,
    path: str | Path = BENCHMARK_PATH,
) -> RedTeamResult:
    """Run the decision layer over the benchmark and return metrics."""
    dataset = load_redteam(path)
    scorer = ConfidenceScorer()
    outcomes: list[dict[str, Any]] = []
    tp = tn = fp = fn = 0
    for case in dataset.cases:
        in_summary, level, score = decide(
            case,
            scorer=scorer,
            min_confidence=min_confidence,
            use_validation=use_validation,
            retrieval_score=retrieval_score,
        )
        expected = case.expected_in_summary
        if expected and in_summary:
            tp += 1
        elif not expected and not in_summary:
            tn += 1
        elif not expected and in_summary:
            fp += 1
        else:
            fn += 1
        outcomes.append(
            {
                "id": case.id,
                "category": case.category,
                "claim": case.claim,
                "evidence_status": case.evidence_status.value,
                "validation_status": case.validation_status.value,
                "confidence_level": level.value,
                "confidence_score": round(score, 3),
                "in_summary": in_summary,
                "expected_in_summary": expected,
                "correct": in_summary == expected,
            }
        )

    total = len(dataset.cases)
    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    fnr = fn / (fn + tp) if (fn + tp) else 0.0
    metrics = RedTeamMetrics(
        total=total,
        true_positive=tp,
        true_negative=tn,
        false_positive=fp,
        false_negative=fn,
        accuracy=round(accuracy, 4),
        precision=round(precision, 4),
        recall=round(recall, 4),
        false_positive_rate=round(fpr, 4),
        false_negative_rate=round(fnr, 4),
    )
    return RedTeamResult(
        version=dataset.version,
        min_confidence=min_confidence,
        use_validation=use_validation,
        cases=outcomes,
        metrics=metrics,
    )


def write_redteam_report(
    result: RedTeamResult,
    output_dir: str | Path = "data/evaluation",
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    tag = "with_validation" if result.use_validation else "baseline"
    path = directory / f"redteam_rda062_{tag}_{timestamp}.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path
