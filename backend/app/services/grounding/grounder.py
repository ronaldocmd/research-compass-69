"""Deterministic grounding classifier (RDA-063).

Combines the safe deterministic checks into a single GroundingResult:

    1. Evidence grounding: is the evidence text present in the chunk?
    2. Number consistency: are the claim's numbers present in the evidence?
    3. Negation consistency: does the claim flip the evidence's negation?

The result is a GroundingStatus that gates the semantic validator: an
UNGROUNDED result makes SUPPORTED impossible regardless of the LLM.

Design notes:
    - Evidence grounding uses normalized substring first, then token overlap
      (tolerating short legitimate paraphrases) — mirroring the existing
      extractor check but with the safe normalization from this module.
    - A number mismatch or negation flip downgrades GROUNDED to
      PARTIALLY_GROUNDED (the evidence is real, but a verifiable fact is
      inconsistent). A direct contradiction (number mismatch on the core
      claim) is treated as UNGROUNDED for the claim's support.
    - UNVERIFIABLE is returned when there is no chunk to check against.
"""

import hashlib
import uuid
from datetime import UTC, datetime

from app.services.grounding.negation import negation_flipped
from app.services.grounding.normalize import normalize, tokenize
from app.services.grounding.numbers import number_mismatches
from app.services.grounding.schemas import (
    GroundingResult,
    GroundingStatus,
    NumberMismatch,
)

# Minimum fraction of evidence tokens that must appear in the chunk for a
# non-exact passage to be accepted as grounded (mirrors the extractor).
_MIN_TOKEN_OVERLAP = 0.6

# Minimum fraction of the claim's content tokens that must appear in the chunk
# for the claim to be considered fully grounded. Below this, the claim has
# substantial content the source does not cover (partial grounding).
_MIN_CLAIM_COVERAGE = 0.6

# A claim is also flagged as partially grounded when it has at least this many
# content tokens that are absent from the chunk (e.g. a compound claim with an
# extra clause), even if the coverage ratio is borderline.
_MIN_UNCOVERED_TOKENS = 2

# Common stopwords (EN + PT) excluded from the claim-coverage computation so
# that function words do not inflate or deflate the coverage ratio.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "in", "on", "at", "to", "for",
    "with", "by", "is", "are", "was", "were", "be", "been", "it", "its", "this",
    "that", "these", "those", "as", "from", "than", "then", "so", "such", "not",
    "no", "o", "a", "os", "as", "um", "uma", "uns", "umas", "e", "ou", "mas",
    "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "para",
    "com", "por", "é", "são", "foi", "foram", "ser", "este", "esta", "isto",
    "isso", "aquele", "aquela", "que", "como", "do", "da", "se", "não",
}


_SUFFIXES = ("ations", "ation", "ings", "ing", "ies", "ed", "es", "s", "ção", "ções", "mente")


def _coverage_stem(token: str) -> str:
    """Strip one common inflectional suffix so paraphrases still match.

    Used ONLY for the claim-coverage check: an LLM that paraphrases the source
    ("increased" vs "increase", "reduces" vs "reduced") must not be penalised
    as uncovered. Never applied to numbers or negation, and only for tokens
    long enough that the stem stays discriminative.
    """
    if token.isdigit():
        return token
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def evidence_is_grounded(evidence_text: str, chunk_text: str) -> bool:
    """Return True when ``evidence_text`` is drawn from ``chunk_text``.

    Normalized-substring match first, then case-insensitive token overlap so
    short paraphrases are tolerated while hallucinations are rejected.
    """
    if not evidence_text or not evidence_text.strip() or not chunk_text:
        return False
    evidence = normalize(evidence_text)
    source = normalize(chunk_text)
    if evidence and evidence in source:
        return True
    evidence_tokens = tokenize(evidence_text)
    source_tokens = set(tokenize(chunk_text))
    if not evidence_tokens:
        return False
    overlap = sum(1 for token in evidence_tokens if token in source_tokens)
    return (overlap / len(evidence_tokens)) >= _MIN_TOKEN_OVERLAP


def _content_hash(text: str) -> str:
    """Return the SHA-256 of ``text`` (for integrity verification)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ground(
    claim_text: str,
    evidence_text: str | None,
    chunk_text: str | None,
    *,
    claim_id: uuid.UUID,
    evidence_id: uuid.UUID,
) -> GroundingResult:
    """Classify the grounding of ``evidence_text`` (for ``claim_text``) against
    ``chunk_text``.

    ``chunk_text`` may be None when the evidence has no chunk reference; the
    result is then UNVERIFIABLE.
    """
    if not chunk_text or not chunk_text.strip():
        return GroundingResult(
            claim_id=claim_id,
            evidence_id=evidence_id,
            status=GroundingStatus.UNVERIFIABLE,
            evidence_grounded=False,
            reason="No source chunk available to verify the evidence against.",
            grounded_at=datetime.now(UTC),
        )

    chunk_hash = _content_hash(chunk_text)

    if not evidence_text or not evidence_text.strip():
        return GroundingResult(
            claim_id=claim_id,
            evidence_id=evidence_id,
            status=GroundingStatus.UNGROUNDED,
            evidence_grounded=False,
            content_hash=chunk_hash,
            reason="No evidence text to ground.",
            grounded_at=datetime.now(UTC),
        )

    grounded = evidence_is_grounded(evidence_text, chunk_text)
    if not grounded:
        return GroundingResult(
            claim_id=claim_id,
            evidence_id=evidence_id,
            status=GroundingStatus.UNGROUNDED,
            evidence_grounded=False,
            content_hash=chunk_hash,
            reason="Evidence text is not present in the source chunk.",
            grounded_at=datetime.now(UTC),
        )

    # Evidence is real. Now check the claim's verifiable facts against the
    # source chunk (the ground truth). The evidence text may itself have been
    # corrupted by the LLM, so the chunk is the authoritative reference.
    mismatches = number_mismatches(claim_text, chunk_text)
    flipped = negation_flipped(claim_text, chunk_text)

    # Claim coverage: does the claim contain substantial content that is not
    # present in the chunk? A compound claim ("X increased ... and caused Y")
    # must not be treated as fully grounded by a passage that only covers part
    # of it. Only meaningful content tokens count (stopwords excluded).
    claim_tokens = [t for t in tokenize(claim_text) if t not in _STOPWORDS]
    chunk_tokens = {_coverage_stem(t) for t in tokenize(chunk_text)}
    if claim_tokens:
        covered = sum(1 for t in claim_tokens if _coverage_stem(t) in chunk_tokens)
        coverage = covered / len(claim_tokens)
        uncovered = len(claim_tokens) - covered
    else:
        coverage = 1.0
        uncovered = 0

    reasons = []
    if mismatches:
        reasons.append(
            "claim numbers not present in evidence: " + ", ".join(mismatches)
        )
    if flipped:
        reasons.append("claim flips the evidence's negation")
    if coverage < _MIN_CLAIM_COVERAGE or uncovered >= _MIN_UNCOVERED_TOKENS:
        reasons.append(
            f"claim content only {coverage:.0%} covered by the source chunk"
        )

    if reasons:
        return GroundingResult(
            claim_id=claim_id,
            evidence_id=evidence_id,
            status=GroundingStatus.PARTIALLY_GROUNDED,
            evidence_grounded=True,
            number_mismatches=[
                NumberMismatch(value=v, source_value=None) for v in mismatches
            ],
            negation_flipped=flipped,
            content_hash=chunk_hash,
            reason="; ".join(reasons),
            grounded_at=datetime.now(UTC),
        )

    return GroundingResult(
        claim_id=claim_id,
        evidence_id=evidence_id,
        status=GroundingStatus.GROUNDED,
        evidence_grounded=True,
        content_hash=chunk_hash,
        reason="Evidence is grounded in the source chunk and the claim's "
        "verifiable facts are consistent.",
        grounded_at=datetime.now(UTC),
    )
