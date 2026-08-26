"""Tests for RDA-048 evidence evaluation."""

import json
import uuid
from pathlib import Path

import pytest

from app.evaluation.evidence import (
    ClaimEvidenceStatus,
    EvidenceEvaluationResult,
    EvidenceEvaluator,
    write_evaluation_report,
)
from scripts.run_benchmark import run_evidence_benchmark
from app.services.claims.schemas import Claim
from app.services.evidence.schemas import Evidence, EvidenceStatus


RESEARCH_ID = uuid.uuid4()


def _claim() -> Claim:
    return Claim(
        claim_id=uuid.uuid4(), text="A grounded claim", chunk_ids=[uuid.uuid4()],
        document_id=uuid.uuid4(), page_number=3, extracted_at="2026-08-26T00:00:00Z",
    )


def _evidence(claim_id: uuid.UUID, *, complete: bool = True) -> Evidence:
    return Evidence(
        evidence_id=uuid.uuid4(), claim_id=claim_id, text="Source passage",
        chunk_id=uuid.uuid4() if complete else None,
        document_id=uuid.uuid4() if complete else None,
        page_number=3 if complete else None, status=EvidenceStatus.SUPPORTED,
        extracted_at="2026-08-26T00:00:00Z",
    )


def test_claims_without_evidence_are_identified() -> None:
    supported = _claim()
    unsupported = _claim()
    evaluator = EvidenceEvaluator(
        claim_loader=lambda _: [supported, unsupported],
        evidence_loader=lambda _: [_evidence(supported.claim_id)],
    )

    result = evaluator.evaluate(RESEARCH_ID)

    assert result.total_claims == 2
    assert result.claims_with_evidence == 1
    assert result.claims_with_evidence_pct == 50
    assert len(result.unsupported_claims) == 1
    assert result.unsupported_claims[0].claim_id == unsupported.claim_id


def test_grounding_and_provenance_rates_are_calculated() -> None:
    grounded = _claim()
    ungrounded = _claim()
    evaluator = EvidenceEvaluator(
        claim_loader=lambda _: [grounded, ungrounded],
        evidence_loader=lambda _: [
            _evidence(grounded.claim_id), _evidence(ungrounded.claim_id, complete=False)
        ],
    )

    result = evaluator.evaluate(RESEARCH_ID)

    assert result.grounding_rate == 50
    assert result.provenance_completeness == 50
    status = evaluator.claim_status(ungrounded, [_evidence(ungrounded.claim_id, complete=False)])
    assert status.has_grounding is False
    assert status.provenance_complete is False


def test_result_contains_all_report_fields() -> None:
    claim = _claim()
    result = EvidenceEvaluator(
        claim_loader=lambda _: [claim], evidence_loader=lambda _: []
    ).evaluate(RESEARCH_ID)

    assert isinstance(result, EvidenceEvaluationResult)
    assert set(result.model_dump()) == {
        "research_id", "total_claims", "claims_with_evidence",
        "claims_with_evidence_pct", "grounding_rate", "provenance_completeness",
        "unsupported_claims",
    }
    assert isinstance(result.unsupported_claims[0], ClaimEvidenceStatus)


def test_report_is_written_as_json(tmp_path: Path) -> None:
    result = EvidenceEvaluationResult(
        research_id=RESEARCH_ID, total_claims=0, claims_with_evidence=0,
        claims_with_evidence_pct=0, grounding_rate=0, provenance_completeness=0,
        unsupported_claims=[],
    )

    report = write_evaluation_report(result, tmp_path)

    assert report.name.startswith("evidence_v1.0_")
    assert report.suffix == ".json"
    assert json.loads(report.read_text(encoding="utf-8"))["total_claims"] == 0


def test_evaluator_requires_data_loaders() -> None:
    with pytest.raises(ValueError, match="claim_loader"):
        EvidenceEvaluator().evaluate(RESEARCH_ID)


def test_benchmark_runner_writes_report_for_research(tmp_path: Path) -> None:
    claim = _claim()
    evaluator = EvidenceEvaluator(
        claim_loader=lambda _: [claim],
        evidence_loader=lambda _: [_evidence(claim.claim_id)],
    )

    reports = __import__("asyncio").run(
        run_evidence_benchmark(
            research_ids=[RESEARCH_ID], evaluator=evaluator, output_dir=tmp_path
        )
    )

    assert len(reports) == 1
    assert reports[0].exists()
