"""baseline: empty initial revision

Purpose (RDA-004): establish the Alembic version chain and create the
`alembic_version` table in PostgreSQL so `alembic upgrade head`,
`alembic current` and `alembic heads` are coherent from day one.

No domain tables are created here on purpose: the Research model/table is
RDA-005 and will arrive as the next revision on top of this baseline.

Revision ID: 0001_baseline
Revises: None
Create Date: 2026-08-13
"""
from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Baseline has no schema changes."""
    pass


def downgrade() -> None:
    """Baseline has no schema changes."""
    pass
