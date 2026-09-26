"""Tests for the deterministic grounding layer (RDA-063)."""

import uuid

from app.services.grounding.grounder import evidence_is_grounded, ground
from app.services.grounding.schemas import GroundingStatus


def _ground(claim, evidence, chunk):
    return ground(
        claim, evidence, chunk,
        claim_id=uuid.uuid4(), evidence_id=uuid.uuid4(),
    )


# --- evidence grounding ------------------------------------------------------


def test_exact_match_is_grounded() -> None:
    result = _ground(
        "Production increased by 12%.",
        "Production increased by 12%.",
        "Production increased by 12% in 2022.",
    )
    assert result.status == GroundingStatus.GROUNDED
    assert result.evidence_grounded is True


def test_nonexistent_sentence_is_ungrounded() -> None:
    result = _ground(
        "X",
        "The company declared bankruptcy in 2023.",
        "Production increased by 12% in 2022.",
    )
    assert result.status == GroundingStatus.UNGROUNDED
    assert result.evidence_grounded is False


def test_whitespace_and_case_are_normalized() -> None:
    result = _ground(
        "Production increased by 12%.",
        "Production  increased   by 12%",
        "production increased by 12%",
    )
    assert result.status == GroundingStatus.GROUNDED


def test_no_chunk_is_unverifiable() -> None:
    result = _ground("X", "some evidence", None)
    assert result.status == GroundingStatus.UNVERIFIABLE


# --- numbers -----------------------------------------------------------------


def test_number_change_is_partially_grounded() -> None:
    result = _ground(
        "Production increased by 21%.",
        "Production increased by 21%.",
        "Production increased by 12%.",
    )
    assert result.status == GroundingStatus.PARTIALLY_GROUNDED
    assert any(m.value == "21%" for m in result.number_mismatches)


def test_equivalent_number_forms_are_grounded() -> None:
    result = _ground(
        "Production increased by 12%.",
        "Production increased by 12%.",
        "Production increased by 12.0%.",
    )
    assert result.status == GroundingStatus.GROUNDED


def test_year_change_is_partially_grounded() -> None:
    result = _ground(
        "The year was 2024.",
        "The year was 2024.",
        "The year was 2023.",
    )
    assert result.status == GroundingStatus.PARTIALLY_GROUNDED


# --- negation ----------------------------------------------------------------


def test_negation_flip_is_partially_grounded() -> None:
    result = _ground(
        "The study found a significant effect.",
        "The study found a significant effect.",
        "The study found no significant effect.",
    )
    assert result.status == GroundingStatus.PARTIALLY_GROUNDED
    assert result.negation_flipped is True


def test_affirmative_claim_against_negative_source_is_partial() -> None:
    result = _ground("There was an increase.", "There was an increase.", "There was no increase.")
    assert result.status == GroundingStatus.PARTIALLY_GROUNDED
    assert result.negation_flipped is True


def test_negative_claim_against_affirmative_source_is_partial() -> None:
    result = _ground("There was no increase.", "There was no increase.", "There was an increase.")
    assert result.status == GroundingStatus.PARTIALLY_GROUNDED
    assert result.negation_flipped is True


def test_negation_is_scoped_to_content_word_in_long_context() -> None:
    result = _ground(
        "The second experiment showed an increase.",
        "The second experiment showed an increase.",
        "The first experiment showed an increase, but the second experiment showed no increase.",
    )
    assert result.status == GroundingStatus.PARTIALLY_GROUNDED
    assert result.negation_flipped is True


def test_same_negative_polarity_remains_grounded() -> None:
    result = _ground("There was no evidence of fraud.", "There was no evidence of fraud.", "There was no evidence of fraud.")
    assert result.status == GroundingStatus.GROUNDED
    assert result.negation_flipped is False


def test_no_negation_flip_is_grounded() -> None:
    result = _ground(
        "The study found a significant effect.",
        "The study found a significant effect.",
        "The study found a significant effect.",
    )
    assert result.status == GroundingStatus.GROUNDED
    assert result.negation_flipped is False


# --- partial grounding -------------------------------------------------------


def test_compound_claim_partially_covered() -> None:
    result = _ground(
        "X increased by 12% in 2022 and caused Y to increase.",
        "X increased by 12% in 2022.",
        "X increased by 12% in 2022.",
    )
    assert result.status == GroundingStatus.PARTIALLY_GROUNDED


def test_full_claim_is_grounded() -> None:
    result = _ground(
        "X increased by 12% in 2022.",
        "X increased by 12% in 2022.",
        "X increased by 12% in 2022.",
    )
    assert result.status == GroundingStatus.GROUNDED


# --- integrity ---------------------------------------------------------------


def test_content_hash_is_present_when_chunk_available() -> None:
    result = _ground("X", "evidence", "chunk text")
    assert result.content_hash is not None
    assert len(result.content_hash) == 64


def test_content_hash_absent_when_no_chunk() -> None:
    result = _ground("X", "evidence", None)
    assert result.content_hash is None
