"""add research plans and plan tasks

Revision ID: 0005_research_plans
Revises: c4544f4654ee
Create Date: 2026-08-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_research_plans"
down_revision: str | None = "c4544f4654ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

plan_status = postgresql.ENUM(
    "CREATED", "RUNNING", "COMPLETED", "FAILED", name="plan_status", create_type=False
)
plan_task_type = postgresql.ENUM(
    "SEARCH", "PROCESS", "EXTRACT", "VALIDATE", "SYNTHESIZE",
    name="plan_task_type",
    create_type=False,
)
plan_task_status = postgresql.ENUM(
    "PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", "SKIPPED",
    name="plan_task_status",
    create_type=False,
)


def upgrade() -> None:
    plan_status.create(op.get_bind(), checkfirst=True)
    plan_task_type.create(op.get_bind(), checkfirst=True)
    plan_task_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "research_plans",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("research_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", plan_status, server_default="CREATED", nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_research_plans"),
        sa.ForeignKeyConstraint(
            ["research_id"],
            ["researches.id"],
            name="fk_research_plans_research_id_researches",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_research_plans_research_id", "research_plans", ["research_id"])

    op.create_table(
        "plan_tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("task_type", plan_task_type, nullable=False),
        sa.Column("status", plan_task_status, server_default="PENDING", nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_plan_tasks"),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["research_plans.id"],
            name="fk_plan_tasks_plan_id_research_plans",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_plan_tasks_plan_id", "plan_tasks", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_plan_tasks_plan_id", table_name="plan_tasks")
    op.drop_table("plan_tasks")
    op.drop_index("ix_research_plans_research_id", table_name="research_plans")
    op.drop_table("research_plans")
    plan_task_status.drop(op.get_bind(), checkfirst=True)
    plan_task_type.drop(op.get_bind(), checkfirst=True)
    plan_status.drop(op.get_bind(), checkfirst=True)
