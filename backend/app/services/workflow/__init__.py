"""Workflow state and execution services."""

__all__ = ["CheckpointManager", "ResearchWorkflowState", "WorkflowStage", "WorkflowOrchestrator"]


def __getattr__(name: str) -> object:
	if name == "CheckpointManager":
		from app.services.workflow.checkpoint_manager import CheckpointManager

		return CheckpointManager
	if name == "WorkflowOrchestrator":
		from app.services.workflow.orchestrator import WorkflowOrchestrator

		return WorkflowOrchestrator
	if name in {"ResearchWorkflowState", "WorkflowStage"}:
		from app.services.workflow.state import ResearchWorkflowState, WorkflowStage

		return {"ResearchWorkflowState": ResearchWorkflowState, "WorkflowStage": WorkflowStage}[name]
	raise AttributeError(name)