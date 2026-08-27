"""create evidence chain tables (claims, evidence, validations, provenance, confidence)

Revision ID: 0006_evidence_chain
Revises: e5f0a8d4b6c2
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_evidence_chain"
down_revision: str | None = "e5f0a8d4b6c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

evidence_status = postgresql.ENUM(
    "supported", "unsupported", "inconclusive",
    name="evidence_status", create_type=False,
)
validation_status = postgresql.ENUM(
    "supported", "partially_supported", "unsupported",
    name="validation_status", create_type=False,
)
confidence_level = postgresql.ENUM(
    "HIGH", "MEDIUM", "LOW",
    name="confidence_level", create_type=False,
)


def upgrade() -> None:
    evidence_status.create(op.get_bind(), checkfirst=True)
    validation_status.create(op.get_bind(), checkfirst=True)
    confidence_level.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "claims",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("chunk_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["research_id"], ["researches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claims_claim_id", "claims", ["claim_id"], unique=True)
    op.create_index("ix_claims_research_id", "claims", ["research_id"])

    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("status", evidence_status, nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.claim_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["research_id"], ["researches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_evidence_id", "evidence", ["evidence_id"], unique=True)
    op.create_index("ix_evidence_research_id", "evidence", ["research_id"])
    op.create_index("ix_evidence_claim_id", "evidence", ["claim_id"])

    op.create_table(
        "validations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("validation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", validation_status, nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_used", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.claim_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.evidence_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["research_id"], ["researches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_validations_validation_id", "validations", ["validation_id"], unique=True)
    op.create_index("ix_validations_research_id", "validations", ["research_id"])
    op.create_index("ix_validations_claim_id", "validations", ["claim_id"])
    op.create_index("ix_validations_evidence_id", "validations", ["evidence_id"])

    op.create_table(
        "provenance",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provenance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chain", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_complete", sa.Boolean(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.claim_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["research_id"], ["researches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provenance_provenance_id", "provenance", ["provenance_id"], unique=True)
    op.create_index("ix_provenance_research_id", "provenance", ["research_id"])
    op.create_index("ix_provenance_claim_id", "provenance", ["claim_id"])

    op.create_table(
        "confidence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("confidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level", confidence_level, nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("factors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.claim_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["research_id"], ["researches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_confidence_confidence_id", "confidence", ["confidence_id"], unique=True)
    op.create_index("ix_confidence_research_id", "confidence", ["research_id"])
    op.create_index("ix_confidence_claim_id", "confidence", ["claim_id"])


def downgrade() -> None:
    op.drop_index("ix_confidence_claim_id", table_name="confidence")
    op.drop_index("ix_confidence_research_id", table_name="confidence")
    op.drop_index("ix_confidence_confidence_id", table_name="confidence")
    op.drop_table("confidence")
    op.drop_index("ix_provenance_claim_id", table_name="provenance")
    op.drop_index("ix_provenance_research_id", table_name="provenance")
    op.drop_index("ix_provenance_provenance_id", table_name="provenance")
    op.drop_table("provenance")
    op.drop_index("ix_validations_evidence_id", table_name="validations")
    op.drop_index("ix_validations_claim_id", table_name="validations")
    op.drop_index("ix_validations_research_id", table_name="validations")
    op.drop_index("ix_validations_validation_id", table_name="validations")
    op.drop_table("validations")
    op.drop_index("ix_evidence_claim_id", table_name="evidence")
    op.drop_index("ix_evidence_research_id", table_name="evidence")
    op.drop_index("ix_evidence_evidence_id", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_claims_research_id", table_name="claims")
    op.drop_index("ix_claims_claim_id", table_name="claims")
    op.drop_table("claims")
    confidence_level.drop(op.get_bind(), checkfirst=True)
    validation_status.drop(op.get_bind(), checkfirst=True)
    evidence_status.drop(op.get_bind(), checkfirst=True)
