"""create documents table and document_status enum

Revision ID: 0003_documents
Revises: 0002_research
Create Date: 2026-08-18
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_documents"
down_revision: str | None = "0002_research"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

document_status = postgresql.ENUM(
    "pending", "downloaded", "processed", "failed", name="document_status", create_type=False
)


def upgrade() -> None:
    document_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("research_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=500), nullable=True),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("authors", postgresql.JSONB(), nullable=False),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("status", document_status, server_default="pending", nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.ForeignKeyConstraint(
            ["research_id"],
            ["researches.id"],
            name="fk_documents_research_id_researches",
            ondelete="CASCADE",
        ),
    )
    # Looking up all documents of a Research is the primary access pattern.
    op.create_index("ix_documents_research_id", "documents", ["research_id"])
    op.create_index("ix_documents_status", "documents", ["status"])


def downgrade() -> None:
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_research_id", table_name="documents")
    op.drop_table("documents")
    document_status.drop(op.get_bind(), checkfirst=True)
