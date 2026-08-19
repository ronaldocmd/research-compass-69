"""Research plan persistence models (RDA-031).

Mirrors the shape of Research (RDA-005) and ChunkRecord (RDA-022). The
``Record`` suffix follows ChunkRecord: ``ResearchPlan`` and ``PlanTask`` are
Pydantic DTOs in app.services.planning.schemas, while these are the ORM
models. ``TaskType``/``TaskStatus`` live here (single source of truth) and
are imported back by app.services.planning.schemas.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PlanStatus(str, enum.Enum):
    """Lifecycle of a ResearchPlan."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskType(str, enum.Enum):
    """The kind of work a planned task represents (shared with RDA-030)."""

    SEARCH = "SEARCH"
    PROCESS = "PROCESS"
    EXTRACT = "EXTRACT"
    VALIDATE = "VALIDATE"
    SYNTHESIZE = "SYNTHESIZE"


class TaskStatus(str, enum.Enum):
    """Lifecycle of a planned task (shared with RDA-030)."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ResearchPlanRecord(Base):
    """The persisted form of a generated ResearchPlan."""

    __tablename__ = "research_plans"

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
    status: Mapped[PlanStatus] = mapped_column(
        Enum(
            PlanStatus,
            name="plan_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=PlanStatus.CREATED,
        server_default=PlanStatus.CREATED.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tasks: Mapped[list["PlanTaskRecord"]] = relationship(
        "PlanTaskRecord",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="PlanTaskRecord.order",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<ResearchPlanRecord id={self.id!s} research_id={self.research_id!s} "
            f"status={self.status.value}>"
        )


class PlanTaskRecord(Base):
    """The persisted form of a single planned task."""

    __tablename__ = "plan_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("research_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    task_type: Mapped[TaskType] = mapped_column(
        Enum(
            TaskType,
            name="plan_task_type",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            name="plan_task_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=TaskStatus.PENDING,
        server_default=TaskStatus.PENDING.value,
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    plan: Mapped["ResearchPlanRecord"] = relationship(
        "ResearchPlanRecord", back_populates="tasks"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<PlanTaskRecord id={self.id!s} type={self.task_type.value} "
            f"status={self.status.value}>"
        )
