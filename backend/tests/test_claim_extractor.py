"""Tests for ClaimExtractor (RDA-025).

The LLMProvider is replaced with a fake in every test: no test performs a
real API call. Source chunks are built as RetrievedChunk DTOs with fixed
UUIDs so claim->chunk association is deterministic.
"""

import uuid

import pytest

from app.services.claims.exceptions import ClaimExtractionError
from app.services.claims.extractor import ClaimExtractor
from app.services.claims.schemas import (
    ClaimDraft,
    ClaimExtractionResponse,
    ClaimExtractionResult,
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
            return response_model(claims=[])
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


def test_extract_multiple_claims_from_rich_text() -> None:
    chunk = _chunk(text="The model X reached 95% accuracy on Y. Technique Z cut latency by 30%.")
    response = ClaimExtractionResponse(claims=[
        ClaimDraft(text="Model X reached 95% accuracy on Y", chunk_ids=[chunk.chunk_id]),
        ClaimDraft(text="Technique Z cut latency by 30%", chunk_ids=[chunk.chunk_id]),
    ])
    extractor = ClaimExtractor(llm=_FakeLLMProvider(response=response))

    result = extractor.extract([chunk], "what were the results?")

    assert isinstance(result, ClaimExtractionResult)
    assert result.total_claims == 2
    assert [c.text for c in result.claims] == [
        "Model X reached 95% accuracy on Y",
        "Technique Z cut latency by 30%",
    ]
    assert all(c.document_id == chunk.document_id for c in result.claims)
    assert all(c.chunk_ids == [chunk.chunk_id] for c in result.claims)
    assert len({c.claim_id for c in result.claims}) == 2


def test_claim_without_chunk_ids_is_discarded() -> None:
    chunk = _chunk(text="source text")
    response = ClaimExtractionResponse(claims=[
        ClaimDraft(text="Supported claim", chunk_ids=[chunk.chunk_id]),
        ClaimDraft(text="Orphan claim", chunk_ids=[]),
    ])
    extractor = ClaimExtractor(llm=_FakeLLMProvider(response=response))

    result = extractor.extract([chunk], "q")

    assert result.total_claims == 1
    assert [c.text for c in result.claims] == ["Supported claim"]


def test_invalid_llm_json_raises_claim_extraction_error() -> None:
    llm = _FakeLLMProvider(error=InvalidLLMResponseError("invalid json"))
    extractor = ClaimExtractor(llm=llm)

    with pytest.raises(ClaimExtractionError):
        extractor.extract([_chunk(text="x")], "q")


def test_llm_provider_error_raises_claim_extraction_error() -> None:
    llm = _FakeLLMProvider(error=LLMProviderError("provider down"))
    extractor = ClaimExtractor(llm=llm)

    with pytest.raises(ClaimExtractionError):
        extractor.extract([_chunk(text="x")], "q")


def test_claim_is_associated_with_correct_chunk() -> None:
    chunk_a = _chunk(text="text a")
    chunk_b = _chunk(text="text b", page_number=7, section="Results")
    response = ClaimExtractionResponse(claims=[
        ClaimDraft(text="Claim from B", chunk_ids=[chunk_b.chunk_id]),
    ])
    extractor = ClaimExtractor(llm=_FakeLLMProvider(response=response))

    result = extractor.extract([chunk_a, chunk_b], "q")

    claim = result.claims[0]
    assert claim.chunk_ids == [chunk_b.chunk_id]
    assert claim.document_id == chunk_b.document_id
    assert claim.page_number == 7


def test_unknown_chunk_ids_are_filtered_out() -> None:
    chunk = _chunk(text="x")
    response = ClaimExtractionResponse(claims=[
        ClaimDraft(text="Claim", chunk_ids=[chunk.chunk_id, uuid.uuid4()]),
    ])
    extractor = ClaimExtractor(llm=_FakeLLMProvider(response=response))

    result = extractor.extract([chunk], "q")

    assert result.claims[0].chunk_ids == [chunk.chunk_id]


def test_claim_with_only_unknown_chunk_ids_is_discarded() -> None:
    chunk = _chunk(text="x")
    response = ClaimExtractionResponse(claims=[
        ClaimDraft(text="Orphan", chunk_ids=[uuid.uuid4()]),
    ])
    extractor = ClaimExtractor(llm=_FakeLLMProvider(response=response))

    result = extractor.extract([chunk], "q")

    assert result.claims == []
    assert result.total_claims == 0


def test_empty_result_when_no_valid_claim() -> None:
    response = ClaimExtractionResponse(claims=[])
    extractor = ClaimExtractor(llm=_FakeLLMProvider(response=response))

    result = extractor.extract([_chunk(text="x")], "q")

    assert result.claims == []
    assert result.total_claims == 0
    assert result.query == "q"
    assert result.model_used == "fake-model"
    assert result.extracted_at is not None


def test_empty_chunks_returns_empty_without_calling_llm() -> None:
    llm = _FakeLLMProvider()
    extractor = ClaimExtractor(llm=llm)

    result = extractor.extract([], "q")

    assert result.claims == []
    assert result.total_claims == 0
    assert llm.prompts == []


def test_prompt_includes_query_and_chunk_ids() -> None:
    chunk = _chunk(text="The model scored 95%.")
    llm = _FakeLLMProvider(response=ClaimExtractionResponse(claims=[]))
    extractor = ClaimExtractor(llm=llm)

    extractor.extract([chunk], "my research question")

    prompt = llm.prompts[0]
    assert "my research question" in prompt
    assert str(chunk.chunk_id) in prompt
    assert chunk.text in prompt
    assert llm.response_models[0] is ClaimExtractionResponse
