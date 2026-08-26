"""Add performance_metrics table

Revision ID: d4e9b7c3f5a1
Revises: c3d8a6b2e4f9
Create Date: 2026-08-26 02:00:00.000000

Written by hand: autogenerate also drops unrelated tables that share the
database, so only the new table is created here.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = 'd4e9b7c3f5a1'
down_revision: str | None = 'c3d8a6b2e4f9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'performance_metrics',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('research_id', sa.UUID(), nullable=False),
        sa.Column('stage', sa.String(length=20), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(['research_id'], ['researches.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_performance_metrics_research_id'), 'performance_metrics', ['research_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_performance_metrics_research_id'), table_name='performance_metrics')
    op.drop_table('performance_metrics')
