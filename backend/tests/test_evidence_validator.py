"""Tests for EvidenceValidator (RDA-028).

The LLMProvider is replaced with a fake in every test: no test performs a
real API call.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.services.claims.schemas import Claim
from app.services.evidence.schemas import Evidence, EvidenceStatus
from app.services.llm.exceptions import InvalidLLMResponseError, LLMProviderError
from app.services.llm.provider import LLMProvider
from app.services.validation.exceptions import ValidationError
from app.services.validation.prompts import build_validation_prompt
from app.services.validation.schemas import ValidationDraft, ValidationStatus
from app.services.validation.validator import EvidenceValidator


class _FakeLLMProvider(LLMProvider):
    name = "fake"

    def __init__(self, *, draft=None, error=None, model="fake-model") -> None:
        self.model = model
        self._draft = draft
        self._error = error
        self.prompts: list[str] = []
        self.response_models: list[type] = []

    def complete(self, prompt, response_model):
        self.prompts.append(prompt)
        self.response_models.append(response_model)
        if self._error is not None:
            raise self._error
        if self._draft is None:
            return response_model(status=ValidationStatus.UNSUPPORTED, reasoning="no draft")
        return self._draft


def _claim(*, text="X reduces latency by 30%", claim_id=None) -> Claim:
    return Claim(
        claim_id=claim_id or uuid.uuid4(),
        text=text,
        chunk_ids=[],
        document_id=uuid.uuid4(),
        page_number=None,
        extracted_at=datetime.now(UTC),
    )


def _evidence(*, text="X showed 30% improvement", status=EvidenceStatus.SUPPORTED, evidence_id=None) -> Evidence:
    return Evidence(
        evidence_id=evidence_id or uuid.uuid4(),
        claim_id=uuid.uuid4(),
        text=text,
        chunk_id=None,
        document_id=None,
        page_number=None,
        status=status,
        extracted_at=datetime.now(UTC),
    )


def test_supported_claim() -> None:
    draft = ValidationDraft(status=ValidationStatus.SUPPORTED, reasoning="The evidence states the claim.")
    validator = EvidenceValidator(llm=_FakeLLMProvider(draft=draft))

    result = validator.validate(_claim(), _evidence())

    assert result.status == ValidationStatus.SUPPORTED
    assert result.reasoning == "The evidence states the claim."


def test_partially_supported_claim() -> None:
    draft = ValidationDraft(status=ValidationStatus.PARTIALLY_SUPPORTED, reasoning="Partially matches.")
    validator = EvidenceValidator(llm=_FakeLLMProvider(draft=draft))

    result = validator.validate(_claim(), _evidence())

    assert result.status == ValidationStatus.PARTIALLY_SUPPORTED


def test_unsupported_claim() -> None:
    draft = ValidationDraft(status=ValidationStatus.UNSUPPORTED, reasoning="Evidence contradicts the claim.")
    validator = EvidenceValidator(llm=_FakeLLMProvider(draft=draft))

    result = validator.validate(_claim(), _evidence())

    assert result.status == ValidationStatus.UNSUPPORTED


def test_evidence_without_text_returns_unsupported_without_llm() -> None:
    llm = _FakeLLMProvider()
    validator = EvidenceValidator(llm=llm)

    result = validator.validate(
        _claim(),
        _evidence(text=None, status=EvidenceStatus.UNSUPPORTED),
    )

    assert result.status == ValidationStatus.UNSUPPORTED
    assert llm.prompts == []


def test_invalid_json_raises_validation_error() -> None:
    llm = _FakeLLMProvider(error=InvalidLLMResponseError("bad json"))
    validator = EvidenceValidator(llm=llm)

    with pytest.raises(ValidationError):
        validator.validate(_claim(), _evidence())


def test_provider_error_raises_validation_error() -> None:
    llm = _FakeLLMProvider(error=LLMProviderError("provider down"))
    validator = EvidenceValidator(llm=llm)

    with pytest.raises(ValidationError):
        validator.validate(_claim(), _evidence())


def test_evidence_text_unchanged_after_validation() -> None:
    evidence = _evidence(text="X showed 30% improvement in response time tests")
    original = evidence.text
    draft = ValidationDraft(status=ValidationStatus.SUPPORTED, reasoning="ok")
    validator = EvidenceValidator(llm=_FakeLLMProvider(draft=draft))

    validator.validate(_claim(), evidence)

    assert evidence.text == original


def test_reasoning_is_non_empty() -> None:
    draft = ValidationDraft(status=ValidationStatus.PARTIALLY_SUPPORTED, reasoning="partial support")
    validator = EvidenceValidator(llm=_FakeLLMProvider(draft=draft))

    result = validator.validate(_claim(), _evidence())

    assert isinstance(result.reasoning, str)
    assert len(result.reasoning) > 0


def test_ids_preserved_in_result() -> None:
    claim = _claim(claim_id=uuid.uuid4())
    evidence = _evidence(evidence_id=uuid.uuid4())
    draft = ValidationDraft(status=ValidationStatus.SUPPORTED, reasoning="ok")
    validator = EvidenceValidator(llm=_FakeLLMProvider(draft=draft))

    result = validator.validate(claim, evidence)

    assert result.claim_id == claim.claim_id
    assert result.evidence_id == evidence.evidence_id
    assert result.validation_id is not None
    assert result.validated_at is not None
    assert result.model_used == "fake-model"


def test_prompt_contains_claim_and_evidence_text() -> None:
    claim = _claim(text="X reduces latency by 30%")
    evidence = _evidence(text="X showed 30% improvement in response time tests")

    prompt = build_validation_prompt(claim, evidence)

    assert "X reduces latency by 30%" in prompt
    assert "X showed 30% improvement in response time tests" in prompt


def test_prompt_does_not_mention_prior_evidence_status() -> None:
    claim = _claim()
    evidence = _evidence(status=EvidenceStatus.INCONCLUSIVE)

    prompt = build_validation_prompt(claim, evidence)

    # "inconclusive" would only appear if the RDA-026 status leaked.
    assert "inconclusive" not in prompt
