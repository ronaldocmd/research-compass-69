"""Tests for RDA-048 evidence evaluation."""

import uuid

import pytest

from app.evaluation.evidence import EvidenceEvaluator, evaluate_evidence
from app.services.evidence.schemas import Evidence, EvidenceStatus


def _evidence(status=EvidenceStatus.SUPPORTED, *, complete=True) -> Evidence:
    return Evidence(
        evidence_id=uuid.uuid4(), claim_id=uuid.uuid4(), text="grounded passage" if status == EvidenceStatus.SUPPORTED else None,
        chunk_id=uuid.uuid4() if complete else None,
        document_id=uuid.uuid4() if complete else None,
        page_number=2 if complete else None,
        status=status,
        extracted_at="2026-08-26T00:00:00Z",
    )


def test_evidence_evaluation_scores_grounding_and_provenance() -> None:
    result = evaluate_evidence([_evidence(), _evidence()])

    assert result.total_evidence == 2
    assert result.grounded_evidence == 2
    assert result.complete_provenance == 2
    assert result.grounding_rate == 1
    assert result.provenance_rate == 1
    assert result.passed is True


def test_unsupported_or_incomplete_evidence_fails() -> None:
    result = EvidenceEvaluator().evaluate([_evidence(), _evidence(EvidenceStatus.UNSUPPORTED, complete=False)])

    assert result.unsupported_evidence == 1
    assert result.complete_provenance == 1
    assert result.grounding_rate == 0.5
    assert result.provenance_rate == 0.5
    assert result.passed is False


def test_empty_evidence_is_not_a_success() -> None:
    result = evaluate_evidence([])

    assert result.total_evidence == 0
    assert result.grounding_rate == 0
    assert result.provenance_rate == 0
    assert result.passed is False


def test_threshold_is_configurable() -> None:
    result = EvidenceEvaluator(min_grounding_rate=0.5).evaluate([_evidence(), _evidence(EvidenceStatus.UNSUPPORTED)])

    assert result.passed is True

    with pytest.raises(ValueError):
        EvidenceEvaluator(min_grounding_rate=1.1)