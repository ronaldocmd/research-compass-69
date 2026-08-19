"""ClaimExtractor (RDA-025).

    RetrievedChunks (RDA-024)
        -> ClaimExtractor
            -> LLMProvider.complete(prompt, ClaimExtractionResponse)
            -> Pydantic validation + provenance filtering
            -> ClaimExtractionResult

The LLM is only ever asked for ``text`` + ``chunk_ids``. Provenance fields
(document_id, page_number) are re-derived server-side from the referenced
source chunks, so a malicious or hallucinated response cannot forge them.
"""

import uuid
from datetime import UTC, datetime

from app.services.claims.exceptions import ClaimExtractionError
from app.services.claims.prompts import build_claim_extraction_prompt
from app.services.claims.schemas import (
    Claim,
    ClaimExtractionResponse,
    ClaimExtractionResult,
)
from app.services.llm.exceptions import InvalidLLMResponseError, LLMProviderError
from app.services.llm.openai_provider import OpenAILLMProvider
from app.services.llm.provider import LLMProvider
from app.services.retrieval.schemas import RetrievedChunk


class ClaimExtractor:
    """Extracts verifiable claims from retrieved chunks via an LLM."""

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self._llm = llm if llm is not None else OpenAILLMProvider()

    def extract(
        self, chunks: list[RetrievedChunk], query: str
    ) -> ClaimExtractionResult:
        """Extract claims from ``chunks`` for ``query``.

        Claims without chunk_ids are discarded silently; chunk_ids that do
        not exist in the input are removed (and a claim left with no valid
        chunk_ids is discarded too).

        Raises:
            ClaimExtractionError: When the LLM returns an invalid/unparsable
                response or the provider fails.
        """
        if not chunks:
            return self._empty_result(query)

        prompt = build_claim_extraction_prompt(query, chunks)
        try:
            response = self._llm.complete(prompt, ClaimExtractionResponse)
        except (InvalidLLMResponseError, LLMProviderError) as exc:
            raise ClaimExtractionError(f"Claim extraction failed: {exc}") from exc

        if not isinstance(response, ClaimExtractionResponse):
            raise ClaimExtractionError(
                f"Expected ClaimExtractionResponse, got {type(response).__name__}"
            )

        claims = self._to_claims(response, chunks)

        return ClaimExtractionResult(
            query=query,
            claims=claims,
            total_claims=len(claims),
            model_used=self._llm.model,
            extracted_at=datetime.now(UTC),
        )

    def _to_claims(
        self, response: ClaimExtractionResponse, chunks: list[RetrievedChunk]
    ) -> list[Claim]:
        chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        claims: list[Claim] = []
        for draft in response.claims:
            if not draft.text or not draft.text.strip():
                continue
            valid_chunk_ids = [
                chunk_id for chunk_id in draft.chunk_ids if chunk_id in chunks_by_id
            ]
            if not valid_chunk_ids:
                continue
            source = chunks_by_id[valid_chunk_ids[0]]
            claims.append(
                Claim(
                    claim_id=uuid.uuid4(),
                    text=draft.text,
                    chunk_ids=valid_chunk_ids,
                    document_id=source.document_id,
                    page_number=source.page_number,
                    extracted_at=datetime.now(UTC),
                )
            )
        return claims

    def _empty_result(self, query: str) -> ClaimExtractionResult:
        return ClaimExtractionResult(
            query=query,
            claims=[],
            total_claims=0,
            model_used=self._llm.model,
            extracted_at=datetime.now(UTC),
        )
