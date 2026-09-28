"""Pydantic response schemas for the evidence chain API (RDA-061).

Expose the persisted claim -> evidence -> source -> provenance -> validation
chain so a research's findings can be recovered after a restart and inspected
independently. Each DTO mirrors the corresponding ORM record.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.services.confidence.schemas import ConfidenceLevel
from app.services.evidence.schemas import EvidenceStatus
from app.services.grounding.schemas import GroundingStatus
from app.services.validation.schemas import ValidationStatus


class ClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    claim_id: uuid.UUID
    research_id: uuid.UUID
    text: str
    document_id: uuid.UUID
    page_number: int | None
    chunk_ids: list[uuid.UUID]
    extracted_at: datetime


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: uuid.UUID
    research_id: uuid.UUID
    claim_id: uuid.UUID
    text: str | None
    chunk_id: uuid.UUID | None
    document_id: uuid.UUID | None
    page_number: int | None
    status: EvidenceStatus
    extracted_at: datetime


class ValidationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    validation_id: uuid.UUID
    research_id: uuid.UUID
    claim_id: uuid.UUID
    evidence_id: uuid.UUID
    status: ValidationStatus
    reasoning: str
    validated_at: datetime
    model_used: str


class ProvenanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provenance_id: uuid.UUID
    research_id: uuid.UUID
    claim_id: uuid.UUID
    chain: list[dict]
    is_complete: bool
    resolved_at: datetime


class ConfidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    confidence_id: uuid.UUID
    research_id: uuid.UUID
    claim_id: uuid.UUID
    level: ConfidenceLevel
    score: float
    reasoning: str
    factors: dict
    scored_at: datetime


class GroundingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    grounding_id: uuid.UUID
    research_id: uuid.UUID
    claim_id: uuid.UUID
    evidence_id: uuid.UUID
    status: GroundingStatus
    evidence_grounded: bool
    number_mismatches: list[dict]
    negation_flipped: bool
    content_hash: str | None
    reason: str
    grounded_at: datetime


class EvidenceChainResponse(BaseModel):
    """The full epistemological chain for one research."""

    research_id: uuid.UUID
    claims: list[ClaimResponse]
    evidence: list[EvidenceResponse]
    validations: list[ValidationResponse]
    provenance: list[ProvenanceResponse]
    confidence: list[ConfidenceResponse]
    groundings: list[GroundingResponse]


class ClaimEvidenceView(BaseModel):
    """Evidence attached to a claim, shaped for the frontend claims page."""

    id: uuid.UUID
    text: str | None
    document_id: uuid.UUID | None
    document_title: str | None
    page_number: int | None


class ClaimView(BaseModel):
    """A claim with its confidence, validation verdict and evidence.

    ``id`` is the claim's stable UUID (``ClaimRecord.claim_id``), not the
    integer surrogate key; ``confidence`` is the 0-1 score.
    """

    id: uuid.UUID
    text: str
    confidence: float | None
    confidence_level: ConfidenceLevel | None
    validation_status: ValidationStatus | None
    document_id: uuid.UUID
    document_title: str | None
    page_number: int | None
    evidence: list[ClaimEvidenceView]
