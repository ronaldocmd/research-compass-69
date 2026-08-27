"""Data access for the epistemological chain tables (RDA-061).

The five entities (claims, evidence, validations, provenance, confidence)
are produced together by the workflow's validation node and read together by
the evidence API, so a single repository persists and reads them as a unit.
Only this layer touches the database; the Service layer depends on it.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence_chain import (
    ClaimRecord,
    ConfidenceRecord,
    EvidenceRecord,
    ProvenanceRecord,
    ValidationRecord,
)
from app.services.workflow.state import ResearchWorkflowState


class EvidenceChainRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def persist(self, state: ResearchWorkflowState) -> None:
        """Insert the chain entities carried by ``state``.

        Idempotent per stable UUID: rows whose claim_id/evidence_id/
        validation_id/provenance_id/confidence_id already exist are skipped,
        so re-running a checkpointed workflow does not duplicate rows. A
        single commit is issued at the end.
        """
        existing_claims = set(
            self.db.scalars(
                select(ClaimRecord.claim_id).where(
                    ClaimRecord.research_id == state.research_id
                )
            )
        )
        existing_evidence = set(
            self.db.scalars(
                select(EvidenceRecord.evidence_id).where(
                    EvidenceRecord.research_id == state.research_id
                )
            )
        )
        existing_validations = set(
            self.db.scalars(
                select(ValidationRecord.validation_id).where(
                    ValidationRecord.research_id == state.research_id
                )
            )
        )
        existing_provenance = set(
            self.db.scalars(
                select(ProvenanceRecord.provenance_id).where(
                    ProvenanceRecord.research_id == state.research_id
                )
            )
        )
        existing_confidence = set(
            self.db.scalars(
                select(ConfidenceRecord.confidence_id).where(
                    ConfidenceRecord.research_id == state.research_id
                )
            )
        )

        for claim in state.claims:
            if claim.claim_id in existing_claims:
                continue
            self.db.add(
                ClaimRecord(
                    claim_id=claim.claim_id,
                    research_id=state.research_id,
                    text=claim.text,
                    document_id=claim.document_id,
                    page_number=claim.page_number,
                    chunk_ids=[str(c) for c in claim.chunk_ids],
                    extracted_at=claim.extracted_at,
                )
            )

        for evidence in state.evidence_items:
            if evidence.evidence_id in existing_evidence:
                continue
            self.db.add(
                EvidenceRecord(
                    evidence_id=evidence.evidence_id,
                    research_id=state.research_id,
                    claim_id=evidence.claim_id,
                    text=evidence.text,
                    chunk_id=evidence.chunk_id,
                    document_id=evidence.document_id,
                    page_number=evidence.page_number,
                    status=evidence.status,
                    extracted_at=evidence.extracted_at,
                )
            )

        for validation in state.validation_results:
            if validation.validation_id in existing_validations:
                continue
            self.db.add(
                ValidationRecord(
                    validation_id=validation.validation_id,
                    research_id=state.research_id,
                    claim_id=validation.claim_id,
                    evidence_id=validation.evidence_id,
                    status=validation.status,
                    reasoning=validation.reasoning,
                    validated_at=validation.validated_at,
                    model_used=validation.model_used,
                )
            )

        for chain in state.provenance_chains:
            if chain.provenance_id in existing_provenance:
                continue
            self.db.add(
                ProvenanceRecord(
                    provenance_id=chain.provenance_id,
                    research_id=state.research_id,
                    claim_id=chain.claim_id,
                    chain=[link.model_dump() for link in chain.chain],
                    is_complete=chain.is_complete,
                    resolved_at=chain.resolved_at,
                )
            )

        for scored in state.scored_claims:
            confidence = scored.confidence
            if confidence.confidence_id in existing_confidence:
                continue
            self.db.add(
                ConfidenceRecord(
                    confidence_id=confidence.confidence_id,
                    research_id=state.research_id,
                    claim_id=scored.claim.claim_id,
                    level=confidence.level,
                    score=confidence.score,
                    reasoning=confidence.reasoning,
                    factors=confidence.factors,
                    scored_at=scored.scored_at,
                )
            )

        self.db.commit()

    def get_claims_by_research(self, research_id: uuid.UUID) -> list[ClaimRecord]:
        return list(
            self.db.scalars(
                select(ClaimRecord)
                .where(ClaimRecord.research_id == research_id)
                .order_by(ClaimRecord.created_at.asc())
            )
        )

    def get_evidence_by_research(self, research_id: uuid.UUID) -> list[EvidenceRecord]:
        return list(
            self.db.scalars(
                select(EvidenceRecord)
                .where(EvidenceRecord.research_id == research_id)
                .order_by(EvidenceRecord.created_at.asc())
            )
        )

    def get_validations_by_research(self, research_id: uuid.UUID) -> list[ValidationRecord]:
        return list(
            self.db.scalars(
                select(ValidationRecord)
                .where(ValidationRecord.research_id == research_id)
                .order_by(ValidationRecord.created_at.asc())
            )
        )

    def get_provenance_by_research(self, research_id: uuid.UUID) -> list[ProvenanceRecord]:
        return list(
            self.db.scalars(
                select(ProvenanceRecord)
                .where(ProvenanceRecord.research_id == research_id)
                .order_by(ProvenanceRecord.created_at.asc())
            )
        )

    def get_confidence_by_research(self, research_id: uuid.UUID) -> list[ConfidenceRecord]:
        return list(
            self.db.scalars(
                select(ConfidenceRecord)
                .where(ConfidenceRecord.research_id == research_id)
                .order_by(ConfidenceRecord.created_at.asc())
            )
        )
