"""REST endpoints for workflow execution (RDA-033)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.orchestration.exceptions import OrchestrationError
from app.services.orchestration.orchestrator import ResearchOrchestrator
from app.services.orchestration.wiring import build_research_nodes, build_workflow_services
from app.services.performance.tracker import PerformanceTracker
from app.services.research_service import ResearchService
from app.services.workflow.state import ResearchWorkflowState, WorkflowStage


class RunRequest(BaseModel):
    """Optional body for ``POST /run``.

    ``focus`` steers a follow-up round on a research that already has results
    (e.g. "impacto ambiental da mineração"); omit it to simply deepen.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    focus: str | None = Field(default=None, max_length=1000)


class ProcessPendingRequest(BaseModel):
    """Optional body for ``POST /process-pending`` (RDA-067)."""

    model_config = ConfigDict(extra="forbid")

    batch_size: int | None = Field(
        default=None, gt=0, le=500,
        description="How many pending documents to work off in this call "
        "(default: settings.PENDING_BATCH_DEFAULT_SIZE).",
    )


class ProcessPendingResponse(BaseModel):
    """Outcome of one process-pending batch."""

    newly_scored: int
    selected: int
    processed: int
    failed: int
    remaining_pending: int


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

# Researches with a run in flight (single-process guard against double-submit,
# which would run the paid pipeline twice and interleave writes).
_running: set[uuid.UUID] = set()


def _orchestrator() -> ResearchOrchestrator:
    """Orchestrator dependency (singleton; overridable in tests)."""
    return _default_orchestrator


def _nodes_factory():
    """Return the factory that builds real workflow nodes (RDA-052).

    Overridable in tests to substitute fake services. The returned callable
    takes ``(db, research_id)`` and returns a ResearchNodes.
    """
    return build_research_nodes


def _services_factory():
    """Return the factory that builds real WorkflowServices (RDA-067).

    Overridable in tests to substitute fake services. The returned callable
    takes ``(db, research_id)`` and returns a WorkflowServices.
    """
    return build_workflow_services


@router.post("/{research_id}/run", response_model=ResearchWorkflowState)
async def run_workflow(
    research_id: uuid.UUID,
    payload: RunRequest | None = None,
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
    if research is None:
        # A run for a non-existent research must not fabricate a COMPLETED
        # state via the default orchestrator (RDA-056).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research {research_id} not found",
        )
    if research_id in _running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A run is already in progress for research {research_id}",
        )
    _running.add(research_id)
    try:
        service.repository.update(research, started_at=datetime.now(UTC))
        orchestrator = ResearchOrchestrator(
            nodes=nodes_factory(db, research_id),
            performance_tracker=PerformanceTracker(db),
        )
        _orchestrators_by_research[research_id] = orchestrator
        state = await orchestrator.run(
            research_id, focus=payload.focus if payload else None
        )
        service.repository.update(research, completed_at=datetime.now(UTC))
        return state
    finally:
        _running.discard(research_id)


@router.post("/{research_id}/process-pending", response_model=ProcessPendingResponse)
def process_pending(
    research_id: uuid.UUID,
    payload: ProcessPendingRequest | None = None,
    db: Session = Depends(get_db),
    services_factory=Depends(_services_factory),
) -> ProcessPendingResponse:
    """Work off already-collected PENDING documents, ranked by fit (RDA-067).

    A search run only downloads/extracts up to the selection cap
    (``max_documents``) of what multi-source search returns; the rest sit as
    "pending" until this is called (repeatedly, if needed) to keep working
    the backlog top-down — no new search calls, no duplicate documents.
    """
    service = ResearchService(db)
    research = service.repository.get(research_id)
    if research is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research {research_id} not found",
        )
    if research_id in _running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A run is already in progress for research {research_id}",
        )
    _running.add(research_id)
    try:
        services = services_factory(db, research_id)
        batch_size = payload.batch_size if payload else None
        stats = services.process_pending_documents(batch_size=batch_size)
        return ProcessPendingResponse(**stats)
    finally:
        _running.discard(research_id)


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
