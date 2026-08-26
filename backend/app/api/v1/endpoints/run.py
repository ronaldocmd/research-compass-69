"""REST endpoints for workflow execution (RDA-033)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.orchestration.exceptions import OrchestrationError
from app.services.orchestration.orchestrator import ResearchOrchestrator
from app.services.orchestration.wiring import build_research_nodes
from app.services.performance.tracker import PerformanceTracker
from app.services.research_service import ResearchService
from app.services.workflow.state import ResearchWorkflowState, WorkflowStage


class WorkflowStatusResponse(ResearchWorkflowState):
    """Workflow state plus the concise stage name used by status clients."""

    stage: WorkflowStage

router = APIRouter()

_default_orchestrator = ResearchOrchestrator()

# Orchestrators created for persisted researches, keyed by research_id, so
# the status endpoint can find the same in-memory execution that a run
# produced (RDA-052). Without this, run_workflow's per-request orchestrator
# would be invisible to workflow_status.
_orchestrators_by_research: dict[uuid.UUID, ResearchOrchestrator] = {}


def _orchestrator() -> ResearchOrchestrator:
    """Orchestrator dependency (singleton; overridable in tests)."""
    return _default_orchestrator


def _nodes_factory():
    """Return the factory that builds real workflow nodes (RDA-052).

    Overridable in tests to substitute fake services. The returned callable
    takes ``(db, research_id)`` and returns a ResearchNodes.
    """
    return build_research_nodes


@router.post("/{research_id}/run", response_model=ResearchWorkflowState)
async def run_workflow(
    research_id: uuid.UUID,
    orchestrator: ResearchOrchestrator = Depends(_orchestrator),
    db: Session = Depends(get_db),
    nodes_factory=Depends(_nodes_factory),
) -> ResearchWorkflowState:
    """Run the workflow, recording start/complete timing and stage metrics.

    When the research exists in the database, the workflow is wired to the
    real services (RDA-052) and the resulting orchestrator is registered so
    ``workflow_status`` can report the same execution. When it does not exist
    (e.g. in-memory orchestration tests), the run proceeds with the injected
    orchestrator and no persistence.
    """
    service = ResearchService(db)
    research = service.repository.get(research_id)
    if research is not None:
        service.repository.update(research, started_at=datetime.now(UTC))
        orchestrator = ResearchOrchestrator(
            nodes=nodes_factory(db, research_id),
            performance_tracker=PerformanceTracker(db),
        )
        _orchestrators_by_research[research_id] = orchestrator
    state = await orchestrator.run(research_id)
    if research is not None:
        service.repository.update(research, completed_at=datetime.now(UTC))
    return state


@router.get("/{research_id}/status", response_model=WorkflowStatusResponse)
async def workflow_status(
    research_id: uuid.UUID,
    orchestrator: ResearchOrchestrator = Depends(_orchestrator),
) -> ResearchWorkflowState:
    active = _orchestrators_by_research.get(research_id, orchestrator)
    try:
        state = await active.get_state_by_research(research_id)
        return WorkflowStatusResponse(**state.model_dump(), stage=state.current_stage)
    except OrchestrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
