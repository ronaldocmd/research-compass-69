"""EvidenceValidator (RDA-028).

    Claim + Evidence (RDA-025/026)
        -> EvidenceValidator
            -> LLMProvider.complete(prompt, ValidationDraft)  # independent call
            -> ValidationResult

The prompt deliberately omits the RDA-026 status so this second, independent
call re-judges the claim<->evidence relationship from scratch.
"""

import uuid
from datetime import UTC, datetime

from app.services.claims.schemas import Claim
from app.services.evidence.schemas import Evidence
from app.services.llm.exceptions import InvalidLLMResponseError, LLMProviderError
from app.services.llm.openai_provider import OpenAILLMProvider
from app.services.llm.provider import LLMProvider
from app.services.validation.exceptions import ValidationError
from app.services.validation.prompts import build_validation_prompt
from app.services.validation.schemas import ValidationDraft, ValidationResult, ValidationStatus


class EvidenceValidator:
    """Independently validates a claim against a piece of evidence."""

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self._llm = llm if llm is not None else OpenAILLMProvider()

    def validate(self, claim: Claim, evidence: Evidence) -> ValidationResult:
        """Validate ``claim`` against ``evidence`` via an independent LLM call.

        Evidence without text (e.g. an ``unsupported`` result with no passage)
        short-circuits to ``unsupported`` without calling the LLM.

        Raises:
            ValidationError: When the LLM returns an invalid response or fails.
        """
        if not evidence.text or not evidence.text.strip():
            return self._unsupported_result(claim, evidence)

        prompt = build_validation_prompt(claim, evidence)
        try:
            draft = self._llm.complete(prompt, ValidationDraft)
        except (InvalidLLMResponseError, LLMProviderError) as exc:
            raise ValidationError(f"Evidence validation failed: {exc}") from exc

        if not isinstance(draft, ValidationDraft):
            raise ValidationError(
                f"Expected ValidationDraft, got {type(draft).__name__}"
            )

        return ValidationResult(
            validation_id=uuid.uuid4(),
            claim_id=claim.claim_id,
            evidence_id=evidence.evidence_id,
            status=draft.status,
            reasoning=draft.reasoning,
            validated_at=datetime.now(UTC),
            model_used=self._llm.model,
        )

    def _unsupported_result(self, claim: Claim, evidence: Evidence) -> ValidationResult:
        return ValidationResult(
            validation_id=uuid.uuid4(),
            claim_id=claim.claim_id,
            evidence_id=evidence.evidence_id,
            status=ValidationStatus.UNSUPPORTED,
            reasoning="No evidence text available; the claim cannot be validated as supported.",
            validated_at=datetime.now(UTC),
            model_used=self._llm.model,
        )
