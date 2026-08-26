"""Budget enforcement and cost accounting for workflow operations."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.workflow.state import ResearchWorkflowState

BudgetOperation = Literal["llm", "search", "processing"]


class BudgetConfig(BaseModel):
    """Configurable resource limits and cost estimates."""

    model_config = ConfigDict(extra="forbid")

    max_llm_calls: int = Field(default=50, ge=0)
    max_search_calls: int = Field(default=20, ge=0)
    max_processing_operations: int = Field(default=100, ge=0)
    max_cost_usd: float = Field(default=5.0, ge=0)
    cost_per_llm_call_usd: float = Field(default=0.01, ge=0)
    cost_per_search_call_usd: float = Field(default=0.005, ge=0)
    cost_per_1k_tokens_usd: float = Field(default=0.002, ge=0)


class BudgetExceededError(RuntimeError):
    """Raised when an operation would exceed the configured budget."""

    def __init__(self, operation: BudgetOperation, detail: str) -> None:
        self.operation = operation
        self.detail = detail
        super().__init__(f"Budget exceeded before {operation}: {detail}")


class BudgetGuard:
    """Check and account for costly workflow operations."""

    def __init__(self, config: BudgetConfig | None = None) -> None:
        self.config = config or BudgetConfig()

    def check_before_llm_call(self, state: ResearchWorkflowState) -> None:
        self._check(state, "llm")

    def check_before_search(self, state: ResearchWorkflowState) -> None:
        self._check(state, "search")

    def check_before_processing(self, state: ResearchWorkflowState) -> None:
        self._check(state, "processing")

    def record_llm_call(
        self, state: ResearchWorkflowState, tokens_used: int = 0
    ) -> ResearchWorkflowState:
        budget = state.budget.model_copy(
            update={
                "llm_calls": state.budget.llm_calls + 1,
                "total_tokens": state.budget.total_tokens + tokens_used,
                "estimated_cost_usd": state.budget.estimated_cost_usd
                + self.config.cost_per_llm_call_usd
                + (tokens_used / 1000) * self.config.cost_per_1k_tokens_usd,
            }
        )
        return self._with_limits(state, budget)

    def record_search_call(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        budget = state.budget.model_copy(
            update={
                "search_calls": state.budget.search_calls + 1,
                "estimated_cost_usd": state.budget.estimated_cost_usd
                + self.config.cost_per_search_call_usd,
            }
        )
        return self._with_limits(state, budget)

    def record_processing(self, state: ResearchWorkflowState) -> ResearchWorkflowState:
        budget = state.budget.model_copy(
            update={
                "processing_operations": state.budget.processing_operations + 1,
            }
        )
        return self._with_limits(state, budget)

    def is_exceeded(self, state: ResearchWorkflowState) -> bool:
        budget = state.budget
        return (
            budget.is_exceeded
            or budget.llm_calls >= self.config.max_llm_calls
            or budget.search_calls >= self.config.max_search_calls
            or budget.processing_operations >= self.config.max_processing_operations
            or budget.estimated_cost_usd >= self.config.max_cost_usd
        )

    def _check(self, state: ResearchWorkflowState, operation: BudgetOperation) -> None:
        budget = state.budget
        if self.is_exceeded(state):
            raise BudgetExceededError(operation, self._details(state))
        limits = {
            "llm": (budget.llm_calls, self.config.max_llm_calls, "llm_calls"),
            "search": (budget.search_calls, self.config.max_search_calls, "search_calls"),
            "processing": (
                budget.processing_operations,
                self.config.max_processing_operations,
                "processing_operations",
            ),
        }
        count, limit, name = limits[operation]
        if count >= limit:
            raise BudgetExceededError(operation, f"{name}={count}, limit={limit}")

    def _with_limits(self, state, budget):
        exceeded = (
            budget.llm_calls >= self.config.max_llm_calls
            or budget.search_calls >= self.config.max_search_calls
            or budget.processing_operations >= self.config.max_processing_operations
            or budget.estimated_cost_usd >= self.config.max_cost_usd
        )
        budget = budget.model_copy(
            update={
                "max_llm_calls": self.config.max_llm_calls,
                "max_search_calls": self.config.max_search_calls,
                "max_processing_operations": self.config.max_processing_operations,
                "max_cost_usd": self.config.max_cost_usd,
                "is_exceeded": budget.is_exceeded or exceeded,
            }
        )
        return state.model_copy(update={"budget": budget})

    def _details(self, state) -> str:
        budget = state.budget
        return (
            f"llm_calls={budget.llm_calls}/{self.config.max_llm_calls}, "
            f"search_calls={budget.search_calls}/{self.config.max_search_calls}, "
            f"processing_operations={budget.processing_operations}/"
            f"{self.config.max_processing_operations}, "
            f"cost_usd={budget.estimated_cost_usd:.4f}/{self.config.max_cost_usd:.4f}"
        )