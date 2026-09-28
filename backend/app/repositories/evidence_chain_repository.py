"""Data access for the epistemological chain tables (RDA-061).

The five entities (claims, evidence, validations, provenance, confidence)
are produced together by the workflow's validation node and read together by
the evidence API, so a single repository persists and reads them as a unit.
Only this layer touches the database; the Service layer depends on it.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.evidence_chain import (
    ClaimRecord,
    ConfidenceRecord,
    EvidenceRecord,
    GroundingRecord,
    ProvenanceRecord,
    ValidationRecord,
)
from app.models.document import Document
from app.schemas.evidence import ClaimEvidenceView, ClaimView
from app.services.validation.schemas import ValidationStatus
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
        existing_groundings = set(
            self.db.scalars(
                select(GroundingRecord.grounding_id).where(
                    GroundingRecord.research_id == state.research_id
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

        for grounding in state.grounding_results:
            if grounding.grounding_id in existing_groundings:
                continue
            self.db.add(
                GroundingRecord(
                    grounding_id=grounding.grounding_id,
                    research_id=state.research_id,
                    claim_id=grounding.claim_id,
                    evidence_id=grounding.evidence_id,
                    status=grounding.status,
                    evidence_grounded=grounding.evidence_grounded,
                    number_mismatches=[
                        m.model_dump() for m in grounding.number_mismatches
                    ],
                    negation_flipped=grounding.negation_flipped,
                    content_hash=grounding.content_hash,
                    reason=grounding.reason,
                    grounded_at=grounding.grounded_at,
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

    def get_groundings_by_research(self, research_id: uuid.UUID) -> list[GroundingRecord]:
        return list(
            self.db.scalars(
                select(GroundingRecord)
                .where(GroundingRecord.research_id == research_id)
                .order_by(GroundingRecord.created_at.asc())
            )
        )

    # A claim is a finding when at least one evidence was validated SUPPORTED
    # (same gate as the synthesis node); otherwise report the strongest
    # negative signal so the UI never shows an unverified claim as verified.
    _STATUS_PRECEDENCE = (
        ValidationStatus.SUPPORTED,
        ValidationStatus.CONTRADICTED,
        ValidationStatus.PARTIALLY_SUPPORTED,
        ValidationStatus.UNSUPPORTED,
    )

    def get_claim_views(
        self, research_id: uuid.UUID, *, limit: int = 200, offset: int = 0
    ) -> tuple[list[ClaimView], int]:
        """Return a page of claims with confidence, validation and evidence.

        Runs a fixed number of queries (claims, evidence, validations,
        confidence, document titles) regardless of how many claims exist, so
        the endpoint does not suffer the N+1 pattern of lazy per-claim loads.
        Returns ``(views, total_claims)``.
        """
        total = (
            self.db.scalar(
                select(func.count())
                .select_from(ClaimRecord)
                .where(ClaimRecord.research_id == research_id)
            )
            or 0
        )
        claims = list(
            self.db.scalars(
                select(ClaimRecord)
                .where(ClaimRecord.research_id == research_id)
                .order_by(ClaimRecord.created_at.asc(), ClaimRecord.id.asc())
                .limit(limit)
                .offset(offset)
            )
        )
        if not claims:
            return [], total
        claim_ids = [c.claim_id for c in claims]

        evidence_by_claim: dict[uuid.UUID, list[EvidenceRecord]] = {}
        for record in self.db.scalars(
            select(EvidenceRecord)
            .where(EvidenceRecord.claim_id.in_(claim_ids))
            .order_by(EvidenceRecord.created_at.asc(), EvidenceRecord.id.asc())
        ):
            evidence_by_claim.setdefault(record.claim_id, []).append(record)

        statuses_by_claim: dict[uuid.UUID, set[ValidationStatus]] = {}
        for claim_id, status in self.db.execute(
            select(ValidationRecord.claim_id, ValidationRecord.status).where(
                ValidationRecord.claim_id.in_(claim_ids)
            )
        ):
            statuses_by_claim.setdefault(claim_id, set()).add(status)

        confidence_by_claim = {
            row.claim_id: row
            for row in self.db.scalars(
                select(ConfidenceRecord)
                .where(ConfidenceRecord.claim_id.in_(claim_ids))
                .order_by(ConfidenceRecord.created_at.asc(), ConfidenceRecord.id.asc())
            )
        }

        document_ids = {c.document_id for c in claims} | {
            e.document_id
            for records in evidence_by_claim.values()
            for e in records
            if e.document_id is not None
        }
        titles = dict(
            self.db.execute(
                select(Document.id, Document.title).where(Document.id.in_(document_ids))
            ).all()
        )

        views = []
        for claim in claims:
            confidence = confidence_by_claim.get(claim.claim_id)
            statuses = statuses_by_claim.get(claim.claim_id, set())
            views.append(
                ClaimView(
                    id=claim.claim_id,
                    text=claim.text,
                    confidence=confidence.score if confidence else None,
                    confidence_level=confidence.level if confidence else None,
                    validation_status=next(
                        (s for s in self._STATUS_PRECEDENCE if s in statuses), None
                    ),
                    document_id=claim.document_id,
                    document_title=titles.get(claim.document_id),
                    page_number=claim.page_number,
                    evidence=[
                        ClaimEvidenceView(
                            id=e.evidence_id,
                            text=e.text,
                            document_id=e.document_id,
                            document_title=titles.get(e.document_id),
                            page_number=e.page_number,
                        )
                        for e in evidence_by_claim.get(claim.claim_id, [])
                    ],
                )
            )
        return views, total
