"""Performance tracking domain model (RDA-051).

One row per workflow stage of a research execution (planning, search,
processing, evidence, synthesis). Rows are append-only so the full history is
kept and metrics (time to first result, time to completion, throughput, error
rate) can be recomputed at any time.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    research_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("researches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "planning" | "search" | "processing" | "evidence" | "synthesis"
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="success"
    )  # "success" | "failed"
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<PerformanceMetric id={self.id!s} research_id={self.research_id!s} "
            f"stage={self.stage!r} status={self.status!r}>"
        )
