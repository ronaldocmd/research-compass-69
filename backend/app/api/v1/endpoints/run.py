"""REST endpoints for workflow execution (RDA-033)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.services.orchestration.exceptions import OrchestrationError
from app.services.orchestration.orchestrator import ResearchOrchestrator
from app.services.workflow.state import ResearchWorkflowState

router = APIRouter()

_default_orchestrator = ResearchOrchestrator()


def _orchestrator() -> ResearchOrchestrator:
    """Orchestrator dependency (singleton; overridable in tests)."""
    return _default_orchestrator


@router.post("/{research_id}/run", response_model=ResearchWorkflowState)
async def run_workflow(
    research_id: uuid.UUID,
    orchestrator: ResearchOrchestrator = Depends(_orchestrator),
) -> ResearchWorkflowState:
    return await orchestrator.run(research_id)


@router.get("/{research_id}/status", response_model=ResearchWorkflowState)
async def workflow_status(
    research_id: uuid.UUID,
    orchestrator: ResearchOrchestrator = Depends(_orchestrator),
) -> ResearchWorkflowState:
    try:
        return await orchestrator.get_state_by_research(research_id)
    except OrchestrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
