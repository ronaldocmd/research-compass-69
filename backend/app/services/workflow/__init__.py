"""Workflow state and execution services."""

from app.services.workflow.exceptions import WorkflowStateError
from app.services.workflow.state import (
    BudgetState,
    ErrorSeverity,
    ResearchWorkflowState,
    WorkflowError,
    WorkflowStage,
)
from app.services.workflow.state_manager import WorkflowStateManager
__all__ = [
    "BudgetState",
    "ErrorSeverity",
    "ResearchWorkflowState",
    "WorkflowError",
    "WorkflowStage",
    "WorkflowStateError",
    "WorkflowStateManager",
    "CheckpointManager",
    "WorkflowOrchestrator",
    "BudgetConfig",
    "BudgetExceededError",
    "BudgetGuard",
]


def __getattr__(name: str) -> object:
    if name == "CheckpointManager":
        from app.services.workflow.checkpoint_manager import CheckpointManager

        return CheckpointManager
    if name == "WorkflowOrchestrator":
        from app.services.workflow.orchestrator import WorkflowOrchestrator

        return WorkflowOrchestrator
    if name in {"BudgetConfig", "BudgetExceededError", "BudgetGuard"}:
        from app.services.workflow.budget_guard import (
            BudgetConfig,
            BudgetExceededError,
            BudgetGuard,
        )

        return {
            "BudgetConfig": BudgetConfig,
            "BudgetExceededError": BudgetExceededError,
            "BudgetGuard": BudgetGuard,
        }[name]
    raise AttributeError(name)
