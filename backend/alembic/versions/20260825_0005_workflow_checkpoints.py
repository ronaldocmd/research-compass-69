"""create workflow checkpoints

Revision ID: 0005_workflow_checkpoints
Revises: c4544f4654ee
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_workflow_checkpoints"
down_revision: str | None = "c4544f4654ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

workflow_stage = postgresql.ENUM(
    "START", "PLANNING", "SEARCH", "SELECTING", "EXTRACTING", "VALIDATING", "COMPLETED",
    name="workflow_stage", create_type=False,
)


def upgrade() -> None:
    workflow_stage.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "workflow_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("research_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", workflow_stage, nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("checkpoint_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_latest", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["research_id"], ["researches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_checkpoints_execution_id", "workflow_checkpoints", ["execution_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_checkpoints_execution_id", table_name="workflow_checkpoints")
    op.drop_table("workflow_checkpoints")
    workflow_stage.drop(op.get_bind(), checkfirst=True)