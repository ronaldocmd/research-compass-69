"""REST endpoints for workflow execution (RDA-033)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.orchestration.exceptions import OrchestrationError
from app.services.orchestration.orchestrator import ResearchOrchestrator
from app.services.performance.tracker import PerformanceTracker
from app.services.research_service import ResearchService
from app.services.workflow.state import ResearchWorkflowState, WorkflowStage


class WorkflowStatusResponse(ResearchWorkflowState):
    """Workflow state plus the concise stage name used by status clients."""

    stage: WorkflowStage

router = APIRouter()

_default_orchestrator = ResearchOrchestrator()


def _orchestrator() -> ResearchOrchestrator:
    """Orchestrator dependency (singleton; overridable in tests)."""
    return _default_orchestrator


@router.post("/{research_id}/run", response_model=ResearchWorkflowState)
async def run_workflow(
    research_id: uuid.UUID,
    orchestrator: ResearchOrchestrator = Depends(_orchestrator),
    db: Session = Depends(get_db),
) -> ResearchWorkflowState:
    """Run the workflow, recording start/complete timing and stage metrics.

    Timing persistence is best-effort: when the research does not exist in
    the database (e.g. in-memory orchestration tests), the run still proceeds
    without persisting timing. When it does exist, a DB-backed
    PerformanceTracker records per-stage timing (RDA-051).
    """
    service = ResearchService(db)
    research = service.repository.get(research_id)
    if research is not None:
        service.repository.update(research, started_at=datetime.now(UTC))
        orchestrator = ResearchOrchestrator(
            performance_tracker=PerformanceTracker(db)
        )
    state = await orchestrator.run(research_id)
    if research is not None:
        service.repository.update(research, completed_at=datetime.now(UTC))
    return state


@router.get("/{research_id}/status", response_model=WorkflowStatusResponse)
async def workflow_status(
    research_id: uuid.UUID,
    orchestrator: ResearchOrchestrator = Depends(_orchestrator),
) -> ResearchWorkflowState:
    try:
        state = await orchestrator.get_state_by_research(research_id)
        return WorkflowStatusResponse(**state.model_dump(), stage=state.current_stage)
    except OrchestrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
