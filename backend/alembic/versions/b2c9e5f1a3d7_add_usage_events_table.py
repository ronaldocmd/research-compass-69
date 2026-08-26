"""Add usage_events table

Revision ID: b2c9e5f1a3d7
Revises: a01d7803a94d
Create Date: 2026-08-26 01:00:00.000000

Written by hand: autogenerate also drops unrelated tables that share the
database, so only the new table is created here.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c9e5f1a3d7'
down_revision: str | None = 'a01d7803a94d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'usage_events',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('research_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(length=20), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=True),
        sa.Column('provider', sa.String(length=100), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['research_id'], ['researches.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_usage_events_research_id'), 'usage_events', ['research_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_usage_events_research_id'), table_name='usage_events')
    op.drop_table('usage_events')
