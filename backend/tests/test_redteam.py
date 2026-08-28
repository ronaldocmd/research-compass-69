"""Tests for the RDA-062 red-team decision-layer evaluation."""

from app.evaluation.redteam import run_redteam


def test_baseline_has_false_positives() -> None:
    """The current decision layer (no validation gate) lets unsupported claims
    reach the summary: causality/generalization (inconclusive -> MEDIUM) and
    fabricated/wrong-chunk (supported -> HIGH) all pass."""
    result = run_redteam(use_validation=False)
    assert result.metrics.false_positive > 0
    assert result.metrics.precision < 1.0


def test_validation_gate_eliminates_false_positives() -> None:
    """With the validation gate, no unsupported claim reaches the summary and
    all genuinely supported claims are still included."""
    result = run_redteam(use_validation=True)
    assert result.metrics.false_positive == 0
    assert result.metrics.false_negative == 0
    assert result.metrics.accuracy == 1.0
    assert result.metrics.precision == 1.0
    assert result.metrics.recall == 1.0


def test_validation_gate_improves_over_baseline() -> None:
    baseline = run_redteam(use_validation=False)
    gated = run_redteam(use_validation=True)
    assert gated.metrics.false_positive < baseline.metrics.false_positive
    assert gated.metrics.accuracy > baseline.metrics.accuracy
