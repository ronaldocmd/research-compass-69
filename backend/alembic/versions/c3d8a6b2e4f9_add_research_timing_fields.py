"""Add research timing fields

Revision ID: c3d8a6b2e4f9
Revises: b2c9e5f1a3d7
Create Date: 2026-08-26 01:30:00.000000

Written by hand: autogenerate also drops unrelated tables that share the
database, so only the new columns are added here.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = 'c3d8a6b2e4f9'
down_revision: str | None = 'b2c9e5f1a3d7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'researches',
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'researches',
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('researches', 'completed_at')
    op.drop_column('researches', 'started_at')
