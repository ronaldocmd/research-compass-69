"""REST endpoint for the evidence chain (RDA-061): /api/v1/researches/{id}/evidence."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.evidence_chain_repository import EvidenceChainRepository
from app.schemas.evidence import (
    ClaimResponse,
    ConfidenceResponse,
    EvidenceChainResponse,
    EvidenceResponse,
    ProvenanceResponse,
    ValidationResponse,
)
from app.services.research_service import ResearchNotFoundError, ResearchService

router = APIRouter()


def _service(db: Session = Depends(get_db)) -> ResearchService:
    return ResearchService(db)


@router.get("/{research_id}/evidence", response_model=EvidenceChainResponse)
def get_evidence_chain(
    research_id: uuid.UUID,
    service: ResearchService = Depends(_service),
    db: Session = Depends(get_db),
) -> EvidenceChainResponse:
    """Return the persisted epistemological chain for a research (RDA-061).

    Recovered from the dedicated tables, so it survives a restart and can be
    inspected independently of the in-memory workflow state.
    """
    try:
        service.get(research_id)
    except ResearchNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    repo = EvidenceChainRepository(db)
    return EvidenceChainResponse(
        research_id=research_id,
        claims=[ClaimResponse.model_validate(c) for c in repo.get_claims_by_research(research_id)],
        evidence=[EvidenceResponse.model_validate(e) for e in repo.get_evidence_by_research(research_id)],
        validations=[
            ValidationResponse.model_validate(v) for v in repo.get_validations_by_research(research_id)
        ],
        provenance=[
            ProvenanceResponse.model_validate(p) for p in repo.get_provenance_by_research(research_id)
        ],
        confidence=[
            ConfidenceResponse.model_validate(c) for c in repo.get_confidence_by_research(research_id)
        ],
    )
