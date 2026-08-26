"""Workflow checkpoint persistence model (RDA-035)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
class WorkflowCheckpoint(Base):
    __tablename__ = "workflow_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    research_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("researches.id", ondelete="CASCADE"), nullable=False,
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    stage: Mapped[str] = mapped_column(
        Enum(
            "START", "PLANNING", "SEARCH", "SELECTING", "EXTRACTING", "VALIDATING", "COMPLETED",
            name="workflow_stage", native_enum=True, validate_strings=True,
        ),
        nullable=False,
    )
    state_json: Mapped[str] = mapped_column(Text, nullable=False)
    checkpoint_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    is_latest: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true",
    )

    research = relationship("Research")