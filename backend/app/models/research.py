"""Research domain model (RDA-005).

Only the model lives here: Repository, Service and API CRUD arrive in
RDA-006+. Status intentionally contains only DRAFT and READY.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ResearchStatus(str, enum.Enum):
    """Allowed lifecycle states for a Research (Documento 80, Sprint 1)."""

    DRAFT = "DRAFT"
    READY = "READY"


class Research(Base):
    __tablename__ = "researches"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ResearchStatus] = mapped_column(
        Enum(
            ResearchStatus,
            name="research_status",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
        default=ResearchStatus.DRAFT,
        server_default=ResearchStatus.DRAFT.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        "Document",
        back_populates="research",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Research id={self.id!s} title={self.title!r} status={self.status.value}>"
