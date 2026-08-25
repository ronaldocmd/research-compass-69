"""Serializable state shared by workflow nodes."""

import enum
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkflowStage(str, enum.Enum):
    START = "START"
    PLANNING = "PLANNING"
    SEARCH = "SEARCH"
    SELECTING = "SELECTING"
    EXTRACTING = "EXTRACTING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"


class ResearchWorkflowState(BaseModel):
    """State persisted between workflow nodes."""

    model_config = ConfigDict(extra="allow")

    research_id: uuid.UUID
    execution_id: uuid.UUID
    current_stage: WorkflowStage = WorkflowStage.START
    search_results: list[Any] = Field(default_factory=list)