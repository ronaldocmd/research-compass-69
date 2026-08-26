"""REST endpoints for workflow execution (RDA-033)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.services.orchestration.exceptions import OrchestrationError
from app.services.orchestration.orchestrator import ResearchOrchestrator
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
) -> ResearchWorkflowState:
    return await orchestrator.run(research_id)


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
