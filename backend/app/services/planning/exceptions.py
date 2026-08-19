"""Domain exceptions for research planning (RDA-030)."""


class PlanningError(Exception):
    """Base class for every error raised by the planning layer."""


class InvalidPlanError(PlanningError):
    """The LLM produced a plan that fails validation."""
