"""Human evaluation domain model (RDA-049).

Stores a single evaluator's rating of one claim so that quality metrics
(inter-rater agreement, average quality) can be computed later. Evaluations
are append-only: old ratings are never deleted when new ones arrive.

``claim_id`` is a plain UUID (no FK): claims are produced by the extraction
service as DTOs and are not persisted in their own table yet. ``research_id``
is stored so evaluations can be queried and aggregated per research, which is
how the API exposes them.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HumanEvaluation(Base):
    __tablename__ = "human_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    research_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    evaluator_id: Mapped[str] = mapped_column(String(255), nullable=False)
    rating: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "correct" | "incorrect" | "inconclusive"
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<HumanEvaluation id={self.id!s} claim_id={self.claim_id!s} "
            f"rating={self.rating!r} evaluator={self.evaluator_id!r}>"
        )
