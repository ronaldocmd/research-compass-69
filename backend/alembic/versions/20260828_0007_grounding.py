"""add groundings table and contradicted validation status (RDA-063)

Revision ID: 0007_grounding
Revises: 0006_evidence_chain
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_grounding"
down_revision: str | None = "0006_evidence_chain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

grounding_status = postgresql.ENUM(
    "grounded", "partially_grounded", "ungrounded", "unverifiable",
    name="grounding_status", create_type=False,
)


def upgrade() -> None:
    # Add the CONTRADICTED value to the existing validation_status enum.
    op.execute("ALTER TYPE validation_status ADD VALUE IF NOT EXISTS 'contradicted'")

    grounding_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "groundings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("grounding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", grounding_status, nullable=False),
        sa.Column("evidence_grounded", sa.Boolean(), nullable=False),
        sa.Column("number_mismatches", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("negation_flipped", sa.Boolean(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("grounded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.claim_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.evidence_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["research_id"], ["researches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_groundings_grounding_id", "groundings", ["grounding_id"], unique=True)
    op.create_index("ix_groundings_research_id", "groundings", ["research_id"])
    op.create_index("ix_groundings_claim_id", "groundings", ["claim_id"])
    op.create_index("ix_groundings_evidence_id", "groundings", ["evidence_id"])


def downgrade() -> None:
    op.drop_index("ix_groundings_evidence_id", table_name="groundings")
    op.drop_index("ix_groundings_claim_id", table_name="groundings")
    op.drop_index("ix_groundings_research_id", table_name="groundings")
    op.drop_index("ix_groundings_grounding_id", table_name="groundings")
    op.drop_table("groundings")
    grounding_status.drop(op.get_bind(), checkfirst=True)
