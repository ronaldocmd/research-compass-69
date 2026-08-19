"""Evidence extraction service (RDA-026)."""

from app.services.evidence.exceptions import EvidenceExtractionError
from app.services.evidence.extractor import EvidenceExtractor, is_text_grounded
from app.services.evidence.prompts import build_evidence_extraction_prompt
from app.services.evidence.schemas import (
    Evidence,
    EvidenceDraft,
    EvidenceExtractionResponse,
    EvidenceExtractionResult,
    EvidenceStatus,
)

__all__ = [
    "Evidence",
    "EvidenceDraft",
    "EvidenceExtractionError",
    "EvidenceExtractionResponse",
    "EvidenceExtractionResult",
    "EvidenceExtractor",
    "EvidenceStatus",
    "build_evidence_extraction_prompt",
    "is_text_grounded",
]
