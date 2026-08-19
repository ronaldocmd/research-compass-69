"""Document domain model (RDA-017).

A Document is a search result (NormalizedSearchResult) persisted against
the Research that found it. Only the model lives here: Repository and
Service live in their own layers, following the same split used by
Research (RDA-005/RDA-006).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

# JSONB on PostgreSQL, plain JSON elsewhere (e.g. SQLite in tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")


class DocumentStatus(str, enum.Enum):
    """Lifecycle of a Document from discovery to processing (RDA-017+)."""

    PENDING = "pending"
    DOWNLOADED = "downloaded"
    PROCESSED = "processed"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"

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
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    authors: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    publication_year: Mapped[int | None] = mapped_column(nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(
            DocumentStatus,
            name="document_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=DocumentStatus.PENDING,
        server_default=DocumentStatus.PENDING.value,
    )
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    file_size: Mapped[int | None] = mapped_column(nullable=True)
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

    research: Mapped["Research"] = relationship("Research", back_populates="documents")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Document id={self.id!s} source={self.source!r} title={self.title!r}>"
