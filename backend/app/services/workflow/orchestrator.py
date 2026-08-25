"""Checkpoint-aware workflow orchestration (RDA-035)."""

import inspect
from collections.abc import Awaitable, Callable, Mapping

from app.services.workflow.checkpoint_manager import CheckpointManager
from app.services.workflow.state import ResearchWorkflowState, WorkflowStage

WorkflowNode = Callable[[ResearchWorkflowState], ResearchWorkflowState | Awaitable[ResearchWorkflowState]]


class WorkflowOrchestrator:
    """Run injected workflow nodes and resume from the latest checkpoint."""

    _stage_order = (
        WorkflowStage.PLANNING,
        WorkflowStage.SEARCH,
        WorkflowStage.SELECTING,
        WorkflowStage.EXTRACTING,
        WorkflowStage.VALIDATING,
        WorkflowStage.COMPLETED,
    )

    def __init__(
        self,
        checkpoint_manager: CheckpointManager,
        nodes: Mapping[WorkflowStage, WorkflowNode],
    ) -> None:
        self.checkpoints = checkpoint_manager
        self.nodes = nodes

    async def run(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        """Run from ``state.current_stage`` or restore the latest checkpoint.

        A checkpoint stores the next stage to execute. Consequently, a
        restart after SEARCH begins at SELECTING and never repeats SEARCH.
        """
        restored = await self.checkpoints.load_latest(str(state.execution_id))
        if restored is not None:
            state = restored

        if state.current_stage == WorkflowStage.COMPLETED:
            return state
        start_index = self._stage_order.index(state.current_stage) if state.current_stage in self._stage_order else 0
        for stage in self._stage_order[start_index:]:
            node = self.nodes.get(stage)
            if node is None:
                raise ValueError(f"No workflow node registered for stage {stage.value}")
            result = node(state)
            state = await result if inspect.isawaitable(result) else result
            if not isinstance(state, ResearchWorkflowState):
                raise TypeError(f"Workflow node {stage.value} must return ResearchWorkflowState")
            next_index = self._stage_order.index(stage) + 1
            state.current_stage = (
                self._stage_order[next_index] if next_index < len(self._stage_order) else WorkflowStage.COMPLETED
            )
            await self.checkpoints.save(state)
            if stage == WorkflowStage.COMPLETED:
                break
        return state
