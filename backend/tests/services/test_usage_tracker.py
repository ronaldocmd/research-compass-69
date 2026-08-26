"""Tests for UsageTracker and cost calculation (RDA-050).

Uses an in-memory SQLite database with the ``usage_events`` table.
"""

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.usage_event import UsageEvent
from app.services.usage.tracker import (
    UsageTracker,
    calculate_llm_cost,
    calculate_search_cost,
)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=[Base.metadata.tables["usage_events"]])
    factory: sessionmaker[Session] = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def test_calculate_llm_cost_known_model() -> None:
    # gpt-4: input 0.03/1k, output 0.06/1k
    cost = calculate_llm_cost("gpt-4", input_tokens=1000, output_tokens=1000)
    assert cost == pytest.approx(0.09)


def test_calculate_llm_cost_unknown_model_is_zero() -> None:
    assert calculate_llm_cost("unknown-model", 1000, 1000) == 0.0


def test_calculate_llm_cost_zero_tokens() -> None:
    assert calculate_llm_cost("gpt-4", 0, 0) == 0.0


def test_calculate_search_cost_free_provider_is_zero() -> None:
    assert calculate_search_cost("openalex") == 0.0
    assert calculate_search_cost("arxiv") == 0.0


def test_calculate_search_cost_unknown_provider_is_zero() -> None:
    assert calculate_search_cost("unknown") == 0.0


def test_record_llm_call_persists_and_computes_cost(db: Session) -> None:
    tracker = UsageTracker(db)
    research_id = uuid.uuid4()

    event = tracker.record_llm_call(research_id, "gpt-4", 1000, 1000)

    assert isinstance(event.id, uuid.UUID)
    assert event.event_type == "llm_call"
    assert event.model == "gpt-4"
    assert event.input_tokens == 1000
    assert event.output_tokens == 1000
    assert event.cost_usd == pytest.approx(0.09)
    assert event.created_at is not None


def test_record_search_call_free_provider_cost_zero(db: Session) -> None:
    tracker = UsageTracker(db)
    event = tracker.record_search_call(uuid.uuid4(), "openalex")

    assert event.event_type == "search"
    assert event.provider == "openalex"
    assert event.cost_usd == 0.0


def test_record_processing_is_free(db: Session) -> None:
    tracker = UsageTracker(db)
    event = tracker.record_processing(
        uuid.uuid4(), documents=3, chunks=12, embeddings=12
    )

    assert event.event_type == "processing"
    assert event.cost_usd == 0.0


def test_get_total_cost_sums_events(db: Session) -> None:
    tracker = UsageTracker(db)
    research_id = uuid.uuid4()
    tracker.record_llm_call(research_id, "gpt-4", 1000, 1000)  # 0.09
    tracker.record_llm_call(research_id, "gpt-3.5-turbo", 1000, 1000)  # 0.0035
    tracker.record_search_call(research_id, "openalex")  # 0.0

    assert tracker.get_total_cost(research_id) == pytest.approx(0.0935)


def test_get_total_cost_empty_research_is_zero(db: Session) -> None:
    assert UsageTracker(db).get_total_cost(uuid.uuid4()) == 0.0


def test_get_report_aggregates_counts(db: Session) -> None:
    tracker = UsageTracker(db)
    research_id = uuid.uuid4()
    tracker.record_llm_call(research_id, "gpt-4", 1000, 500)
    tracker.record_llm_call(research_id, "gpt-4", 200, 100)
    tracker.record_search_call(research_id, "openalex")
    tracker.record_processing(research_id, documents=1, chunks=4, embeddings=4)

    report = tracker.get_report(research_id)

    assert report["research_id"] == research_id
    assert report["llm_calls"] == 2
    assert report["total_tokens"] == (1000 + 500) + (200 + 100)
    assert report["search_calls"] == 1
    assert report["processing_operations"] == 1
    assert report["estimated_cost_usd"] == pytest.approx(
        calculate_llm_cost("gpt-4", 1000, 500)
        + calculate_llm_cost("gpt-4", 200, 100)
    )


def test_get_report_empty_research(db: Session) -> None:
    report = UsageTracker(db).get_report(uuid.uuid4())

    assert report["llm_calls"] == 0
    assert report["total_tokens"] == 0
    assert report["search_calls"] == 0
    assert report["processing_operations"] == 0
    assert report["estimated_cost_usd"] == 0.0


def test_events_are_append_only(db: Session) -> None:
    tracker = UsageTracker(db)
    research_id = uuid.uuid4()
    tracker.record_llm_call(research_id, "gpt-4", 100, 100)
    tracker.record_llm_call(research_id, "gpt-4", 200, 200)

    events = list(
        db.execute(
            select(UsageEvent).where(UsageEvent.research_id == research_id)
        ).scalars()
    )
    assert len(events) == 2
