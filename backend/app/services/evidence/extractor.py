"""EvidenceExtractor (RDA-026).

    Claim + RetrievedChunks (of the claim's chunk_ids)
        -> EvidenceExtractor
            -> LLMProvider.complete(prompt, EvidenceExtractionResponse)
            -> grounding validation (text must come from a source chunk)
            -> EvidenceExtractionResult

The LLM only ever returns ``text`` + ``chunk_id`` + ``status``. The text is
validated server-side against the referenced chunk (substring or token
overlap) so a hallucinated passage is never returned as evidence.
"""

import re
import uuid
from datetime import UTC, datetime

from app.services.claims.schemas import Claim
from app.services.evidence.exceptions import EvidenceExtractionError
from app.services.evidence.prompts import build_evidence_extraction_prompt
from app.services.evidence.schemas import (
    Evidence,
    EvidenceDraft,
    EvidenceExtractionResponse,
    EvidenceExtractionResult,
    EvidenceStatus,
)
from app.services.llm.exceptions import InvalidLLMResponseError, LLMProviderError
from app.services.llm.openai_provider import OpenAILLMProvider
from app.services.llm.provider import LLMProvider
from app.services.retrieval.schemas import RetrievedChunk

# Minimum fraction of evidence tokens that must appear in the source chunk
# for a non-exact passage to be accepted as grounded.
_MIN_TOKEN_OVERLAP = 0.6


def is_text_grounded(evidence_text: str, chunk_text: str) -> bool:
    """Return True when ``evidence_text`` is drawn from ``chunk_text``.

    Checks a normalized-substring match first (the common case: the LLM
    copied a passage verbatim), then falls back to case-insensitive token
    overlap so short paraphrases are tolerated while blatant hallucinations
    are rejected.
    """
    if not evidence_text or not evidence_text.strip() or not chunk_text:
        return False

    evidence = _normalize(evidence_text)
    source = _normalize(chunk_text)
    if evidence in source:
        return True

    evidence_tokens = re.findall(r"\w+", evidence.lower())
    source_tokens = set(re.findall(r"\w+", source.lower()))
    if not evidence_tokens:
        return False

    overlap = sum(1 for token in evidence_tokens if token in source_tokens)
    return (overlap / len(evidence_tokens)) >= _MIN_TOKEN_OVERLAP


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class EvidenceExtractor:
    """Locates, for a claim, the exact passages that support it."""

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self._llm = llm if llm is not None else OpenAILLMProvider()

    def extract(
        self, claim: Claim, chunks: list[RetrievedChunk]
    ) -> EvidenceExtractionResult:
        """Extract evidence for ``claim`` from the provided ``chunks``.

        Only chunks referenced by ``claim.chunk_ids`` are considered. When
        none are available, the result is ``unsupported`` and the LLM is not
        called.

        Raises:
            EvidenceExtractionError: When the LLM returns an invalid response
                or the provider fails.
        """
        referenced = [c for c in chunks if c.chunk_id in claim.chunk_ids]
        if not referenced:
            return self._unsupported_result(claim)

        prompt = build_evidence_extraction_prompt(claim, referenced)
        try:
            response = self._llm.complete(prompt, EvidenceExtractionResponse)
        except (InvalidLLMResponseError, LLMProviderError) as exc:
            raise EvidenceExtractionError(f"Evidence extraction failed: {exc}") from exc

        if not isinstance(response, EvidenceExtractionResponse):
            raise EvidenceExtractionError(
                f"Expected EvidenceExtractionResponse, got {type(response).__name__}"
            )

        chunks_by_id = {chunk.chunk_id: chunk for chunk in referenced}
        evidence = [
            self._to_evidence(claim, draft, chunks_by_id)
            for draft in response.evidence
        ]

        return EvidenceExtractionResult(
            claim_id=claim.claim_id,
            evidence=evidence,
            final_status=self._aggregate(evidence),
            extracted_at=datetime.now(UTC),
        )

    def _to_evidence(
        self,
        claim: Claim,
        draft: EvidenceDraft,
        chunks_by_id: dict[uuid.UUID, RetrievedChunk],
    ) -> Evidence:
        chunk = chunks_by_id.get(draft.chunk_id) if draft.chunk_id else None
        text = draft.text
        grounded = bool(text and chunk and is_text_grounded(text, chunk.text))

        if grounded:
            return Evidence(
                evidence_id=uuid.uuid4(),
                claim_id=claim.claim_id,
                text=text,
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                page_number=chunk.page_number,
                status=draft.status,
                extracted_at=datetime.now(UTC),
            )

        # No grounded passage: a "supported" claim without evidence text is
        # downgraded to "unsupported"; hallucinated text is never returned.
        status = draft.status
        if status == EvidenceStatus.SUPPORTED:
            status = EvidenceStatus.UNSUPPORTED

        return Evidence(
            evidence_id=uuid.uuid4(),
            claim_id=claim.claim_id,
            text=None,
            chunk_id=None,
            document_id=None,
            page_number=None,
            status=status,
            extracted_at=datetime.now(UTC),
        )

    @staticmethod
    def _aggregate(evidence: list[Evidence]) -> EvidenceStatus:
        statuses = {item.status for item in evidence}
        if EvidenceStatus.SUPPORTED in statuses:
            return EvidenceStatus.SUPPORTED
        if EvidenceStatus.INCONCLUSIVE in statuses:
            return EvidenceStatus.INCONCLUSIVE
        return EvidenceStatus.UNSUPPORTED

    def _unsupported_result(self, claim: Claim) -> EvidenceExtractionResult:
        return EvidenceExtractionResult(
            claim_id=claim.claim_id,
            evidence=[],
            final_status=EvidenceStatus.UNSUPPORTED,
            extracted_at=datetime.now(UTC),
        )
