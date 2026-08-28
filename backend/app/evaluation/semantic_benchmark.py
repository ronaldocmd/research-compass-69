"""RDA-064 semantic validation benchmark.

Runs the real EvidenceValidator (LLM) against a labelled gold benchmark of
claim/evidence pairs that are textually grounded but semantically varied
(supported, paraphrased, causal, generalized, antonym, scope, temporal,
conditional, relevant-but-not-supporting, semantically-fabricated).

Measures how reliably the semantic validator distinguishes these cases, and
reports accuracy, precision, recall, F1, FPR, FNR plus a confusion matrix.

This is a live benchmark (makes real LLM calls) and is not part of the unit
suite. It is driven by a script, not by pytest.
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.claims.schemas import Claim
from app.services.evidence.schemas import Evidence, EvidenceStatus
from app.services.validation.schemas import ValidationStatus
from app.services.validation.validator import EvidenceValidator

BENCHMARK_PATH = Path(__file__).parents[2] / "data" / "benchmarks" / "semantic_rda064_v1.json"

# The states the system actually uses for semantic validation.
STATES = [
    ValidationStatus.SUPPORTED,
    ValidationStatus.PARTIALLY_SUPPORTED,
    ValidationStatus.UNSUPPORTED,
    ValidationStatus.CONTRADICTED,
]


class SemanticCase(BaseModel):
    """One labelled semantic case."""

    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
    claim: str
    evidence: str
    expected: ValidationStatus


class SemanticDataset(BaseModel):
    """A versioned collection of semantic cases."""

    model_config = ConfigDict(extra="forbid")

    version: str
    created_at: datetime
    description: str | None = None
    cases: list[SemanticCase] = Field(min_length=1)


class SemanticMetrics(BaseModel):
    """Aggregate metrics over the benchmark."""

    model_config = ConfigDict(extra="forbid")

    total: int
    correct: int
    accuracy: float
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    false_negative_rate: float
    # Dangerous errors: unsupported/contradicted/partial predicted as supported.
    unsupported_to_supported: int
    contradicted_to_supported: int
    partial_to_supported: int


class SemanticRunResult(BaseModel):
    """Per-case outcomes plus aggregate metrics for one run."""

    model_config = ConfigDict(extra="forbid")

    version: str
    run_id: str
    cases: list[dict[str, Any]]
    metrics: SemanticMetrics
    confusion: dict[str, dict[str, int]]


def load_semantic_benchmark(path: str | Path = BENCHMARK_PATH) -> SemanticDataset:
    raw = Path(path).read_text(encoding="utf-8")
    return SemanticDataset.model_validate(json.loads(raw))


def _claim(text: str) -> Claim:
    return Claim(
        claim_id=uuid.uuid4(), text=text, chunk_ids=[uuid.uuid4()],
        document_id=uuid.uuid4(), page_number=1, extracted_at=datetime.now(UTC),
    )


def _evidence(claim: Claim, text: str) -> Evidence:
    return Evidence(
        evidence_id=uuid.uuid4(), claim_id=claim.claim_id, text=text,
        chunk_id=claim.chunk_ids[0], document_id=claim.document_id,
        page_number=1, status=EvidenceStatus.SUPPORTED,
        extracted_at=datetime.now(UTC),
    )


def _is_supported(status: ValidationStatus) -> bool:
    return status == ValidationStatus.SUPPORTED


def run_semantic_benchmark(
    validator: EvidenceValidator | None = None,
    path: str | Path = BENCHMARK_PATH,
    run_id: str | None = None,
    verbose: bool = False,
) -> SemanticRunResult:
    """Run the semantic validator over the benchmark and return metrics."""
    dataset = load_semantic_benchmark(path)
    validator = validator or EvidenceValidator()
    run_id = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    outcomes: list[dict[str, Any]] = []
    confusion: dict[str, dict[str, int]] = {
        s.value: {t.value: 0 for t in STATES} for s in STATES
    }

    for case in dataset.cases:
        claim = _claim(case.claim)
        evidence = _evidence(claim, case.evidence)
        try:
            result = validator.validate(claim, evidence)
            actual = result.status
        except Exception as exc:  # noqa: BLE001
            actual = f"ERROR:{type(exc).__name__}"
        expected = case.expected
        ok = actual == expected
        if isinstance(actual, ValidationStatus):
            confusion[expected.value][actual.value] += 1
        if verbose:
            actual_s = actual.value if isinstance(actual, ValidationStatus) else actual
            print(
                f"  [{case.id}] {case.category:24s} expected={expected.value:20s} "
                f"actual={actual_s:20s} {'OK' if ok else 'MISS'}",
                flush=True,
            )
        outcomes.append(
            {
                "id": case.id,
                "category": case.category,
                "claim": case.claim,
                "evidence": case.evidence,
                "expected": expected.value,
                "actual": actual.value if isinstance(actual, ValidationStatus) else actual,
                "correct": ok,
            }
        )

    total = len(dataset.cases)
    correct = sum(1 for c in outcomes if c["correct"])
    # Binary view for precision/recall/F1: supported vs not-supported.
    tp = sum(
        1
        for c in outcomes
        if c["expected"] == "supported" and c["actual"] == "supported"
    )
    fp = sum(
        1
        for c in outcomes
        if c["expected"] != "supported" and c["actual"] == "supported"
    )
    fn = sum(
        1
        for c in outcomes
        if c["expected"] == "supported" and c["actual"] != "supported"
    )
    tn = total - tp - fp - fn
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    fnr = fn / (fn + tp) if (fn + tp) else 0.0

    unsupported_to_supported = sum(
        1
        for c in outcomes
        if c["expected"] in ("unsupported", "contradicted", "partially_supported")
        and c["actual"] == "supported"
    )
    contradicted_to_supported = sum(
        1
        for c in outcomes
        if c["expected"] == "contradicted" and c["actual"] == "supported"
    )
    partial_to_supported = sum(
        1
        for c in outcomes
        if c["expected"] == "partially_supported" and c["actual"] == "supported"
    )

    metrics = SemanticMetrics(
        total=total,
        correct=correct,
        accuracy=round(correct / total, 4),
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        false_positive_rate=round(fpr, 4),
        false_negative_rate=round(fnr, 4),
        unsupported_to_supported=unsupported_to_supported,
        contradicted_to_supported=contradicted_to_supported,
        partial_to_supported=partial_to_supported,
    )
    return SemanticRunResult(
        version=dataset.version,
        run_id=run_id,
        cases=outcomes,
        metrics=metrics,
        confusion=confusion,
    )


def write_semantic_report(
    result: SemanticRunResult,
    output_dir: str | Path = "data/evaluation",
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"semantic_rda064_{result.run_id}.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path
