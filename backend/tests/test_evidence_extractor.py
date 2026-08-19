"""Tests for EvidenceExtractor (RDA-026).

The LLMProvider is replaced with a fake in every test: no test performs a
real API call.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.services.claims.schemas import Claim
from app.services.evidence.exceptions import EvidenceExtractionError
from app.services.evidence.extractor import EvidenceExtractor, is_text_grounded
from app.services.evidence.schemas import (
    EvidenceDraft,
    EvidenceExtractionResponse,
    EvidenceStatus,
)
from app.services.llm.exceptions import InvalidLLMResponseError, LLMProviderError
from app.services.llm.provider import LLMProvider
from app.services.retrieval.schemas import RetrievedChunk


class _FakeLLMProvider(LLMProvider):
    name = "fake"

    def __init__(self, *, response=None, error=None, model="fake-model") -> None:
        self.model = model
        self._response = response
        self._error = error
        self.prompts: list[str] = []
        self.response_models: list[type] = []

    def complete(self, prompt, response_model):
        self.prompts.append(prompt)
        self.response_models.append(response_model)
        if self._error is not None:
            raise self._error
        if self._response is None:
            return response_model(evidence=[])
        return self._response


def _chunk(
    *,
    text,
    chunk_id=None,
    document_id=None,
    page_number=1,
    section=None,
    document_title=None,
    score=0.9,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id or uuid.uuid4(),
        document_id=document_id or uuid.uuid4(),
        text=text,
        page_number=page_number,
        section=section,
        score=score,
        document_title=document_title,
    )


def _claim(*, text="A claim", chunk_ids=None, claim_id=None, document_id=None) -> Claim:
    return Claim(
        claim_id=claim_id or uuid.uuid4(),
        text=text,
        chunk_ids=chunk_ids if chunk_ids is not None else [],
        document_id=document_id or uuid.uuid4(),
        page_number=None,
        extracted_at=datetime.now(UTC),
    )


def test_supported_when_strong_evidence_found() -> None:
    chunk = _chunk(text="Results showed X achieved 95.2% accuracy on benchmark Y.")
    claim = _claim(text="Model X reached 95% accuracy", chunk_ids=[chunk.chunk_id])
    response = EvidenceExtractionResponse(evidence=[
        EvidenceDraft(
            text="X achieved 95.2% accuracy on benchmark Y",
            chunk_id=chunk.chunk_id,
            status=EvidenceStatus.SUPPORTED,
        ),
    ])
    extractor = EvidenceExtractor(llm=_FakeLLMProvider(response=response))

    result = extractor.extract(claim, [chunk])

    assert result.final_status == EvidenceStatus.SUPPORTED
    assert len(result.evidence) == 1
    assert result.evidence[0].status == EvidenceStatus.SUPPORTED
    assert result.evidence[0].text == "X achieved 95.2% accuracy on benchmark Y"


def test_inconclusive_when_chunks_available_but_no_clear_support() -> None:
    chunk = _chunk(text="X showed mixed results across different configurations.")
    claim = _claim(text="X is always better", chunk_ids=[chunk.chunk_id])
    response = EvidenceExtractionResponse(evidence=[
        EvidenceDraft(
            text="mixed results across different configurations",
            chunk_id=chunk.chunk_id,
            status=EvidenceStatus.INCONCLUSIVE,
        ),
    ])
    extractor = EvidenceExtractor(llm=_FakeLLMProvider(response=response))

    result = extractor.extract(claim, [chunk])

    assert result.final_status == EvidenceStatus.INCONCLUSIVE
    assert result.evidence[0].status == EvidenceStatus.INCONCLUSIVE


def test_unsupported_when_no_chunks_provided() -> None:
    claim = _claim(text="Some claim", chunk_ids=[uuid.uuid4()])
    llm = _FakeLLMProvider()
    extractor = EvidenceExtractor(llm=llm)

    result = extractor.extract(claim, [])

    assert result.final_status == EvidenceStatus.UNSUPPORTED
    assert result.evidence == []
    assert llm.prompts == []


def test_evidence_text_is_extracted_from_chunk_not_generated() -> None:
    chunk = _chunk(text="The new method cut latency by 30 percent.")
    claim = _claim(text="The method cuts latency", chunk_ids=[chunk.chunk_id])
    response = EvidenceExtractionResponse(evidence=[
        EvidenceDraft(
            text="cut latency by 30 percent",
            chunk_id=chunk.chunk_id,
            status=EvidenceStatus.SUPPORTED,
        ),
    ])
    extractor = EvidenceExtractor(llm=_FakeLLMProvider(response=response))

    result = extractor.extract(claim, [chunk])

    assert result.evidence[0].text == "cut latency by 30 percent"


def test_hallucinated_evidence_text_is_rejected() -> None:
    chunk = _chunk(text="The system improved F1 by 12 points.")
    claim = _claim(text="The system is best", chunk_ids=[chunk.chunk_id])
    response = EvidenceExtractionResponse(evidence=[
        EvidenceDraft(
            text="The moon is made of green cheese",
            chunk_id=chunk.chunk_id,
            status=EvidenceStatus.SUPPORTED,
        ),
    ])
    extractor = EvidenceExtractor(llm=_FakeLLMProvider(response=response))

    result = extractor.extract(claim, [chunk])

    assert result.final_status == EvidenceStatus.UNSUPPORTED
    assert result.evidence[0].status == EvidenceStatus.UNSUPPORTED
    assert result.evidence[0].text is None


def test_invalid_llm_response_raises_evidence_extraction_error() -> None:
    chunk = _chunk(text="some text")
    claim = _claim(text="a claim", chunk_ids=[chunk.chunk_id])
    llm = _FakeLLMProvider(error=InvalidLLMResponseError("bad json"))
    extractor = EvidenceExtractor(llm=llm)

    with pytest.raises(EvidenceExtractionError):
        extractor.extract(claim, [chunk])


def test_llm_provider_error_raises_evidence_extraction_error() -> None:
    chunk = _chunk(text="some text")
    claim = _claim(text="a claim", chunk_ids=[chunk.chunk_id])
    llm = _FakeLLMProvider(error=LLMProviderError("provider down"))
    extractor = EvidenceExtractor(llm=llm)

    with pytest.raises(EvidenceExtractionError):
        extractor.extract(claim, [chunk])


def test_provenance_preserved_from_chunk() -> None:
    chunk = _chunk(text="X achieved 95.2% accuracy.", page_number=7, section="Results")
    claim = _claim(text="X achieved 95% accuracy", chunk_ids=[chunk.chunk_id])
    response = EvidenceExtractionResponse(evidence=[
        EvidenceDraft(
            text="X achieved 95.2% accuracy",
            chunk_id=chunk.chunk_id,
            status=EvidenceStatus.SUPPORTED,
        ),
    ])
    extractor = EvidenceExtractor(llm=_FakeLLMProvider(response=response))

    result = extractor.extract(claim, [chunk])

    evidence = result.evidence[0]
    assert evidence.chunk_id == chunk.chunk_id
    assert evidence.document_id == chunk.document_id
    assert evidence.page_number == 7
    assert evidence.claim_id == claim.claim_id


def test_final_status_supported_dominates() -> None:
    chunk = _chunk(text="A and B.")
    claim = _claim(text="A", chunk_ids=[chunk.chunk_id])
    response = EvidenceExtractionResponse(evidence=[
        EvidenceDraft(text="A", chunk_id=chunk.chunk_id, status=EvidenceStatus.INCONCLUSIVE),
        EvidenceDraft(text="A", chunk_id=chunk.chunk_id, status=EvidenceStatus.SUPPORTED),
    ])
    extractor = EvidenceExtractor(llm=_FakeLLMProvider(response=response))

    result = extractor.extract(claim, [chunk])

    assert result.final_status == EvidenceStatus.SUPPORTED


def test_is_text_grounded_exact_substring() -> None:
    assert is_text_grounded("95.2% accuracy", "Results showed 95.2% accuracy.") is True


def test_is_text_grounded_rejects_foreign_text() -> None:
    assert is_text_grounded("totally unrelated words", "Results showed 95.2% accuracy.") is False


def test_is_text_grounded_empty_text() -> None:
    assert is_text_grounded("", "anything") is False
    assert is_text_grounded("   ", "anything") is False
