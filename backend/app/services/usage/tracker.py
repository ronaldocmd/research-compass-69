"""UsageTracker: persistent cost accounting for research executions (RDA-050).

Each costly operation (LLM call, search call, processing) is recorded as a
``UsageEvent`` row. Costs are derived from the explicit pricing config
(``LLM_PRICING`` / ``SEARCH_PRICING``) — never invented or hardcoded here.
Free operations (e.g. free search providers) are recorded with cost 0.0.

The tracker is a thin persistence layer; the workflow's in-memory
``BudgetGuard`` continues to enforce limits during execution.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.usage_event import UsageEvent


def calculate_llm_cost(
    model: str, input_tokens: int, output_tokens: int
) -> float:
    """Estimate the USD cost of one LLM call from the pricing config.

    Returns 0.0 when the model has no configured price (unknown model).
    """
    pricing = settings.LLM_PRICING.get(model)
    if not pricing:
        return 0.0
    cost = (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])
    return round(cost, 6)


def calculate_search_cost(provider: str) -> float:
    """Return the configured per-call cost for a search provider (0.0 if free)."""
    return float(settings.SEARCH_PRICING.get(provider, 0.0))


class UsageTracker:
    """Persists usage events and aggregates cost per research."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def record_llm_call(
        self,
        research_id: uuid.UUID,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> UsageEvent:
        """Record one LLM call and persist its estimated cost."""
        cost = calculate_llm_cost(model, input_tokens, output_tokens)
        event = UsageEvent(
            research_id=research_id,
            event_type="llm_call",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def record_search_call(
        self, research_id: uuid.UUID, provider: str
    ) -> UsageEvent:
        """Record one search call. Free providers are stored with cost 0.0."""
        cost = calculate_search_cost(provider)
        event = UsageEvent(
            research_id=research_id,
            event_type="search",
            provider=provider,
            cost_usd=cost,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def record_processing(
        self,
        research_id: uuid.UUID,
        *,
        documents: int = 0,
        chunks: int = 0,
        embeddings: int = 0,
    ) -> UsageEvent:
        """Record a processing operation. Processing is free (cost 0.0)."""
        event = UsageEvent(
            research_id=research_id,
            event_type="processing",
            input_tokens=documents,
            output_tokens=chunks + embeddings,
            cost_usd=0.0,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def get_total_cost(self, research_id: uuid.UUID) -> float:
        """Return the summed estimated cost (USD) for a research."""
        total = self.db.execute(
            select(func.coalesce(func.sum(UsageEvent.cost_usd), 0.0)).where(
                UsageEvent.research_id == research_id
            )
        ).scalar_one()
        return round(float(total), 6)

    def get_report(self, research_id: uuid.UUID) -> dict:
        """Aggregate usage for a research into a cost report.

        Returns llm_calls, total_tokens, search_calls, processing_operations,
        estimated_cost_usd and duration_seconds (0 when no timing recorded).
        """
        events = list(
            self.db.execute(
                select(UsageEvent).where(UsageEvent.research_id == research_id)
            ).scalars()
        )
        llm_calls = sum(1 for e in events if e.event_type == "llm_call")
        search_calls = sum(1 for e in events if e.event_type == "search")
        processing_operations = sum(1 for e in events if e.event_type == "processing")
        # total_tokens counts LLM tokens only; processing counts are tracked
        # separately and must not pollute the token total.
        total_tokens = sum(
            (e.input_tokens or 0) + (e.output_tokens or 0)
            for e in events
            if e.event_type == "llm_call"
        )
        return {
            "research_id": research_id,
            "llm_calls": llm_calls,
            "total_tokens": total_tokens,
            "search_calls": search_calls,
            "processing_operations": processing_operations,
            "estimated_cost_usd": self.get_total_cost(research_id),
        }
