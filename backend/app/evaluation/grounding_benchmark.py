"""RDA-063 grounding-layer benchmark evaluation.

Runs the deterministic grounding layer against a labelled benchmark of
adversarial claim/evidence/chunk cases and reports how accurately it classifies
each case into the grounding taxonomy (GROUNDED / PARTIALLY_GROUNDED /
UNGROUNDED / UNVERIFIABLE).

Fully deterministic and reproducible: no LLM is involved. This measures the
deterministic gate that now protects the semantic validator.
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.grounding.grounder import ground
from app.services.grounding.schemas import GroundingStatus

BENCHMARK_PATH = Path(__file__).parents[2] / "data" / "benchmarks" / "grounding_rda063_v1.json"


class GroundingCase(BaseModel):
    """One labelled adversarial case for the grounding layer."""

    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
    claim: str
    evidence: str
    chunk: str | None
    expected: GroundingStatus


class GroundingDataset(BaseModel):
    """A versioned collection of grounding cases."""

    model_config = ConfigDict(extra="forbid")

    version: str
    created_at: datetime
    description: str | None = None
    cases: list[GroundingCase] = Field(min_length=1)


class GroundingMetrics(BaseModel):
    """Aggregate grounding accuracy over the benchmark."""

    model_config = ConfigDict(extra="forbid")

    total: int
    correct: int
    accuracy: float
    # Per-category accuracy.
    by_category: dict[str, dict[str, int | float]]


class GroundingBenchmarkResult(BaseModel):
    """Per-case grounding outcomes plus aggregate metrics."""

    model_config = ConfigDict(extra="forbid")

    version: str
    cases: list[dict[str, Any]]
    metrics: GroundingMetrics


def load_grounding_benchmark(path: str | Path = BENCHMARK_PATH) -> GroundingDataset:
    raw = Path(path).read_text(encoding="utf-8")
    return GroundingDataset.model_validate(json.loads(raw))


def run_grounding_benchmark(
    path: str | Path = BENCHMARK_PATH,
) -> GroundingBenchmarkResult:
    """Run the grounding layer over the benchmark and return metrics."""
    dataset = load_grounding_benchmark(path)
    outcomes: list[dict[str, Any]] = []
    by_category: dict[str, dict[str, int | float]] = {}
    correct = 0
    for case in dataset.cases:
        result = ground(
            case.claim,
            case.evidence,
            case.chunk,
            claim_id=uuid.uuid4(),
            evidence_id=uuid.uuid4(),
        )
        ok = result.status == case.expected
        if ok:
            correct += 1
        cat = by_category.setdefault(
            case.category, {"total": 0, "correct": 0, "accuracy": 0.0}
        )
        cat["total"] += 1
        if ok:
            cat["correct"] += 1
        outcomes.append(
            {
                "id": case.id,
                "category": case.category,
                "claim": case.claim,
                "expected": case.expected.value,
                "actual": result.status.value,
                "negation_flipped": result.negation_flipped,
                "number_mismatches": [m.value for m in result.number_mismatches],
                "correct": ok,
            }
        )

    for cat in by_category.values():
        cat["accuracy"] = round(cat["correct"] / cat["total"], 4)

    total = len(dataset.cases)
    return GroundingBenchmarkResult(
        version=dataset.version,
        cases=outcomes,
        metrics=GroundingMetrics(
            total=total,
            correct=correct,
            accuracy=round(correct / total, 4),
            by_category=by_category,
        ),
    )


def write_grounding_report(
    result: GroundingBenchmarkResult,
    output_dir: str | Path = "data/evaluation",
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"grounding_rda063_{timestamp}.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path
