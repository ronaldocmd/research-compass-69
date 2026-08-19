"""DTOs for research planning (RDA-030).

``TaskType``/``TaskStatus`` live in app.models.plan (RDA-031) so the same
enums are shared by the planner DTOs and the persisted PlanTask model.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.plan import TaskStatus, TaskType


class ResearchPlanInput(BaseModel):
    """Input the caller provides to generate a research plan."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    research_id: uuid.UUID
    objective: str = Field(min_length=1, max_length=5000)
    question: str = Field(min_length=1, max_length=2000)
    language: str = "en"
    depth: Literal["basic", "standard", "deep"] = "standard"
    sources: list[str] = Field(default_factory=list)


class PlanTask(BaseModel):
    """A single prioritized task within a research plan."""

    model_config = ConfigDict(extra="forbid")

    task_id: uuid.UUID
    title: str
    description: str
    priority: int  # 1-5, 1 = highest priority
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING


class ResearchPlan(BaseModel):
    """A structured plan of tasks for one research."""

    model_config = ConfigDict(extra="forbid")

    plan_id: uuid.UUID
    research_id: uuid.UUID
    tasks: list[PlanTask]
    created_at: datetime


class PlanTaskDraft(BaseModel):
    """What the LLM returns for a single task (task_type is a raw string)."""

    model_config = ConfigDict(extra="forbid")

    title: str
    description: str
    priority: int
    task_type: str


class ResearchPlanResponse(BaseModel):
    """Structured-output contract handed to the LLMProvider (RDA-030)."""

    model_config = ConfigDict(extra="forbid")

    tasks: list[PlanTaskDraft]
