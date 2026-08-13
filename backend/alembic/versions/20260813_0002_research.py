"""create researches table and research_status enum

Revision ID: 0002_research
Revises: 0001_baseline
Create Date: 2026-08-13
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_research"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

research_status = postgresql.ENUM("DRAFT", "READY", name="research_status", create_type=False)


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    research_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "researches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", research_status, server_default="DRAFT", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_researches"),
    )
    # Listing by status is the only access pattern known at this stage.
    op.create_index("ix_researches_status", "researches", ["status"])


def downgrade() -> None:
    op.drop_index("ix_researches_status", table_name="researches")
    op.drop_table("researches")
    research_status.drop(op.get_bind(), checkfirst=True)
