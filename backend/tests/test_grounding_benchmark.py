"""Tests for the RDA-063 grounding-layer benchmark."""

from app.evaluation.grounding_benchmark import run_grounding_benchmark


def test_grounding_benchmark_high_accuracy() -> None:
    """The deterministic grounding layer correctly classifies the adversarial
    cases: fabricated and wrong-chunk evidence are UNGROUNDED, number changes
    and negation flips are PARTIALLY_GROUNDED, supported claims are GROUNDED."""
    result = run_grounding_benchmark()
    assert result.metrics.accuracy >= 0.9


def test_grounding_benchmark_catches_fabricated_and_wrong_chunk() -> None:
    """Fabricated evidence and wrong-chunk evidence must be UNGROUNDED."""
    result = run_grounding_benchmark()
    for case in result.cases:
        if case["category"] in ("fabricated", "wrong_chunk"):
            assert case["actual"] == "ungrounded", case["id"]


def test_grounding_benchmark_catches_number_changes() -> None:
    """Number changes must be PARTIALLY_GROUNDED."""
    result = run_grounding_benchmark()
    for case in result.cases:
        if case["category"] == "number":
            assert case["actual"] == "partially_grounded", case["id"]
