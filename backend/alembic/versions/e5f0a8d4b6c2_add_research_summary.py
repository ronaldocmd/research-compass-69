"""Add research summary column

Revision ID: e5f0a8d4b6c2
Revises: d4e9b7c3f5a1
Create Date: 2026-08-26 03:00:00.000000

Written by hand: autogenerate also drops unrelated tables that share the
database, so only the new column is added here.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = 'e5f0a8d4b6c2'
down_revision: str | None = 'd4e9b7c3f5a1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('researches', sa.Column('summary', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('researches', 'summary')
