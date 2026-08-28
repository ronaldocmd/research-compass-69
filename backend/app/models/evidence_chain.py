"""ORM models for the epistemological chain (RDA-061).

Persists the claim -> evidence -> source -> provenance -> validation chain
produced by the workflow so claims can be recovered after a restart and
distinguished from unsupported statements. Each entity mirrors the DTO in
app.services.{claims,evidence,validation,provenance,confidence}.schemas and
is keyed by its stable UUID (the same convention used by ChunkRecord).

The enums are imported from the service schemas so the column types match
the DTOs exactly (same pattern as Document.status).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base
from app.services.confidence.schemas import ConfidenceLevel
from app.services.evidence.schemas import EvidenceStatus
from app.services.grounding.schemas import GroundingStatus
from app.services.validation.schemas import ValidationStatus

# JSONB on PostgreSQL, plain JSON elsewhere (e.g. SQLite in tests). Same
# pattern used for Document.document_metadata (RDA-017) and ChunkRecord.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class ClaimRecord(Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    research_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("researches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(JSONType, nullable=False, default=list)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EvidenceRecord(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    research_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("researches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("claims.claim_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[EvidenceStatus] = mapped_column(
        Enum(
            EvidenceStatus,
            name="evidence_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ValidationRecord(Base):
    __tablename__ = "validations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    validation_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    research_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("researches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("claims.claim_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("evidence.evidence_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ValidationStatus] = mapped_column(
        Enum(
            ValidationStatus,
            name="validation_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model_used: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProvenanceRecord(Base):
    __tablename__ = "provenance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provenance_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    research_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("researches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("claims.claim_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chain: Mapped[list[dict]] = mapped_column(JSONType, nullable=False, default=list)
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConfidenceRecord(Base):
    __tablename__ = "confidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    confidence_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    research_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("researches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("claims.claim_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    level: Mapped[ConfidenceLevel] = mapped_column(
        Enum(
            ConfidenceLevel,
            name="confidence_level",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    factors: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GroundingRecord(Base):
    """Deterministic grounding outcome for one claim/evidence pair (RDA-063)."""

    __tablename__ = "groundings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grounding_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    research_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("researches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("claims.claim_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("evidence.evidence_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[GroundingStatus] = mapped_column(
        Enum(
            GroundingStatus,
            name="grounding_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    evidence_grounded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    number_mismatches: Mapped[list[dict]] = mapped_column(
        JSONType, nullable=False, default=list
    )
    negation_flipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    grounded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
