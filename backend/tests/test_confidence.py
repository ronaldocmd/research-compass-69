"""Tests for ConfidenceScorer (RDA-027).

Pure deterministic logic: no LLM and no mocks are needed.
"""

import uuid
from datetime import UTC, datetime

from app.services.claims.schemas import Claim
from app.services.confidence.scorer import ConfidenceScorer
from app.services.confidence.schemas import ConfidenceLevel, ConfidenceScore, ScoredClaim
from app.services.evidence.schemas import Evidence, EvidenceStatus
from app.services.grounding.schemas import GroundingStatus


def _claim(*, chunk_ids=None) -> Claim:
    return Claim(
        claim_id=uuid.uuid4(),
        text="Some claim",
        chunk_ids=chunk_ids if chunk_ids is not None else [],
        document_id=uuid.uuid4(),
        page_number=None,
        extracted_at=datetime.now(UTC),
    )


def _evidence(*, status, chunk_id=None, text="evidence text") -> Evidence:
    return Evidence(
        evidence_id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        text=text,
        chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        page_number=1,
        status=status,
        extracted_at=datetime.now(UTC),
    )


def test_supported_with_high_retrieval_is_high() -> None:
    chunk_id = uuid.uuid4()
    claim = _claim(chunk_ids=[chunk_id])
    evidence = [_evidence(status=EvidenceStatus.SUPPORTED, chunk_id=chunk_id)]
    scorer = ConfidenceScorer()

    result = scorer.score(claim, evidence, retrieval_scores={chunk_id: 0.9})

    assert result.level == ConfidenceLevel.HIGH
    assert result.score >= 0.75


def test_inconclusive_is_medium() -> None:
    claim = _claim(chunk_ids=[uuid.uuid4()])
    scorer = ConfidenceScorer()

    result = scorer.score(claim, [_evidence(status=EvidenceStatus.INCONCLUSIVE)])

    assert result.level == ConfidenceLevel.MEDIUM


def test_unsupported_is_low() -> None:
    claim = _claim(chunk_ids=[uuid.uuid4()])
    scorer = ConfidenceScorer()

    result = scorer.score(claim, [_evidence(status=EvidenceStatus.UNSUPPORTED)])

    assert result.level == ConfidenceLevel.LOW


def test_empty_evidence_is_low() -> None:
    claim = _claim(chunk_ids=[uuid.uuid4()])
    scorer = ConfidenceScorer()

    result = scorer.score(claim, [])

    assert result.level == ConfidenceLevel.LOW
    assert result.score == 0.0


def test_multiple_supported_scores_higher_than_single() -> None:
    claim = _claim(chunk_ids=[uuid.uuid4()])
    scorer = ConfidenceScorer()

    single = scorer.score(claim, [_evidence(status=EvidenceStatus.SUPPORTED)])
    multiple = scorer.score(
        claim,
        [
            _evidence(status=EvidenceStatus.SUPPORTED),
            _evidence(status=EvidenceStatus.SUPPORTED),
        ],
    )

    assert multiple.score > single.score


def test_factors_contain_expected_keys() -> None:
    claim = _claim(chunk_ids=[uuid.uuid4()])
    scorer = ConfidenceScorer()

    result = scorer.score(claim, [_evidence(status=EvidenceStatus.SUPPORTED)])

    assert set(result.factors) >= {
        "evidence_strength",
        "retrieval_score",
        "coverage",
    }


def test_reasoning_is_non_empty_and_readable() -> None:
    claim = _claim(chunk_ids=[uuid.uuid4()])
    scorer = ConfidenceScorer()

    result = scorer.score(claim, [_evidence(status=EvidenceStatus.SUPPORTED)])

    assert isinstance(result.reasoning, str)
    assert len(result.reasoning) > 0


def test_low_reasoning_signals_not_confirmed() -> None:
    claim = _claim(chunk_ids=[uuid.uuid4()])
    scorer = ConfidenceScorer()

    result = scorer.score(claim, [_evidence(status=EvidenceStatus.UNSUPPORTED)])

    assert result.level == ConfidenceLevel.LOW
    assert "must not be treated as" in result.reasoning


def test_score_is_within_bounds() -> None:
    chunk_id = uuid.uuid4()
    claim = _claim(chunk_ids=[chunk_id])
    scorer = ConfidenceScorer()

    result = scorer.score(
        claim,
        [
            _evidence(status=EvidenceStatus.SUPPORTED, chunk_id=chunk_id),
            _evidence(status=EvidenceStatus.SUPPORTED, chunk_id=chunk_id),
        ],
        retrieval_scores={chunk_id: 0.95},
    )

    assert 0.0 <= result.score <= 1.0


def test_retrieval_scores_are_optional() -> None:
    claim = _claim(chunk_ids=[uuid.uuid4()])
    scorer = ConfidenceScorer()

    result = scorer.score(claim, [_evidence(status=EvidenceStatus.SUPPORTED)])

    assert result.level == ConfidenceLevel.MEDIUM  # 0.6


def test_medium_retrieval_gives_medium_level() -> None:
    chunk_id = uuid.uuid4()
    claim = _claim(chunk_ids=[chunk_id])
    scorer = ConfidenceScorer()

    result = scorer.score(
        claim,
        [_evidence(status=EvidenceStatus.SUPPORTED, chunk_id=chunk_id)],
        retrieval_scores={chunk_id: 0.8},
    )

    # 0.6 base + 0.1 (0.70 < 0.8 <= 0.85) = 0.7 -> MEDIUM, not HIGH.
    assert result.level == ConfidenceLevel.MEDIUM
    assert result.score == 0.7


def test_score_claim_returns_scored_claim() -> None:
    chunk_id = uuid.uuid4()
    claim = _claim(chunk_ids=[chunk_id])
    evidence = [_evidence(status=EvidenceStatus.SUPPORTED, chunk_id=chunk_id)]
    scorer = ConfidenceScorer()

    scored = scorer.score_claim(claim, evidence, retrieval_scores={chunk_id: 0.9})

    assert isinstance(scored, ScoredClaim)
    assert scored.claim == claim
    assert scored.evidence == evidence
    assert isinstance(scored.confidence, ConfidenceScore)
    assert scored.scored_at is not None



# --- RDA-063: grounding gate in the confidence scorer ------------------------


def _grounding(status, *, negation_flipped=False):
    from app.services.grounding.schemas import GroundingResult, GroundingStatus

    return GroundingResult(
        claim_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        status=status,
        evidence_grounded=status == GroundingStatus.GROUNDED,
        negation_flipped=negation_flipped,
        reason="test",
    )


def test_ungrounded_evidence_caps_confidence_to_low() -> None:
    """RDA-063: an UNGROUNDED evidence cannot yield HIGH confidence even with
    high retrieval and a SUPPORTED extractor status."""
    chunk_id = uuid.uuid4()
    claim = _claim(chunk_ids=[chunk_id])
    evidence = [_evidence(status=EvidenceStatus.SUPPORTED, chunk_id=chunk_id)]
    grounding = [_grounding(GroundingStatus.UNGROUNDED)]

    result = ConfidenceScorer().score(
        claim, evidence, retrieval_scores={chunk_id: 0.9}, grounding_results=grounding
    )

    assert result.level == ConfidenceLevel.LOW
    assert result.factors.get("grounding") == "UNGROUNDED"


def test_partially_grounded_caps_confidence_to_medium() -> None:
    """RDA-063: a PARTIALLY_GROUNDED evidence caps confidence at MEDIUM."""
    chunk_id = uuid.uuid4()
    claim = _claim(chunk_ids=[chunk_id])
    evidence = [_evidence(status=EvidenceStatus.SUPPORTED, chunk_id=chunk_id)]
    grounding = [_grounding(GroundingStatus.PARTIALLY_GROUNDED)]

    result = ConfidenceScorer().score(
        claim, evidence, retrieval_scores={chunk_id: 0.9}, grounding_results=grounding
    )

    assert result.level == ConfidenceLevel.MEDIUM


def test_unverifiable_caps_confidence_to_medium() -> None:
    """RDA-063: an UNVERIFIABLE evidence (no chunk) caps confidence at MEDIUM."""
    chunk_id = uuid.uuid4()
    claim = _claim(chunk_ids=[chunk_id])
    evidence = [_evidence(status=EvidenceStatus.SUPPORTED, chunk_id=chunk_id)]
    grounding = [_grounding(GroundingStatus.UNVERIFIABLE)]

    result = ConfidenceScorer().score(
        claim, evidence, retrieval_scores={chunk_id: 0.9}, grounding_results=grounding
    )

    assert result.level == ConfidenceLevel.MEDIUM


def test_grounded_evidence_keeps_high_confidence() -> None:
    """RDA-063: a GROUNDED evidence with high retrieval keeps HIGH confidence."""
    chunk_id = uuid.uuid4()
    claim = _claim(chunk_ids=[chunk_id])
    evidence = [_evidence(status=EvidenceStatus.SUPPORTED, chunk_id=chunk_id)]
    grounding = [_grounding(GroundingStatus.GROUNDED)]

    result = ConfidenceScorer().score(
        claim, evidence, retrieval_scores={chunk_id: 0.9}, grounding_results=grounding
    )

    assert result.level == ConfidenceLevel.HIGH
    assert result.factors.get("grounding") == "GROUNDED"


def test_grounding_results_are_optional_backwards_compatible() -> None:
    """RDA-063: without grounding results the scorer behaves as before."""
    chunk_id = uuid.uuid4()
    claim = _claim(chunk_ids=[chunk_id])
    evidence = [_evidence(status=EvidenceStatus.SUPPORTED, chunk_id=chunk_id)]

    result = ConfidenceScorer().score(
        claim, evidence, retrieval_scores={chunk_id: 0.9}
    )

    assert result.level == ConfidenceLevel.HIGH
