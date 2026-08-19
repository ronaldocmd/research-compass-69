"""add file storage columns to documents

Revision ID: 0004_document_storage
Revises: 0003_documents
Create Date: 2026-08-18
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_document_storage"
down_revision: str | None = "0003_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("file_hash", sa.String(length=64), nullable=True))
    op.add_column("documents", sa.Column("storage_path", sa.String(length=1000), nullable=True))
    op.add_column("documents", sa.Column("file_size", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "file_size")
    op.drop_column("documents", "storage_path")
    op.drop_column("documents", "file_hash")
