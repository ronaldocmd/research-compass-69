"""Tests for PerformanceTracker and metric calculations (RDA-051).

Uses an in-memory SQLite database with the ``performance_metrics`` table.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.performance_metric import PerformanceMetric
from app.services.performance.tracker import (
    PerformanceTracker,
    calculate_error_rate,
    calculate_throughput,
    calculate_time_to_completion,
    calculate_time_to_first_result,
)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables["performance_metrics"]]
    )
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


def _metric(
    stage: str,
    started_at: datetime,
    completed_at: datetime | None,
    status: str = "success",
) -> PerformanceMetric:
    return PerformanceMetric(
        research_id=uuid.uuid4(),
        stage=stage,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=(
            (completed_at - started_at).total_seconds() if completed_at else None
        ),
        status=status,
    )


def test_start_and_end_stage_records_duration(db: Session) -> None:
    tracker = PerformanceTracker(db)
    research_id = uuid.uuid4()

    tracker.start_stage(research_id, "planning")
    metric = tracker.end_stage(research_id, "planning")

    assert metric is not None
    assert metric.stage == "planning"
    assert metric.status == "success"
    assert metric.completed_at is not None
    assert metric.duration_seconds is not None
    assert metric.duration_seconds >= 0


def test_end_stage_without_start_returns_none(db: Session) -> None:
    tracker = PerformanceTracker(db)
    assert tracker.end_stage(uuid.uuid4(), "planning") is None


def test_end_stage_records_failure(db: Session) -> None:
    tracker = PerformanceTracker(db)
    research_id = uuid.uuid4()
    tracker.start_stage(research_id, "search")

    metric = tracker.end_stage(
        research_id, "search", status="failed", error_message="boom"
    )

    assert metric.status == "failed"
    assert metric.error_message == "boom"


def test_get_metrics_returns_only_that_research(db: Session) -> None:
    tracker = PerformanceTracker(db)
    research_a = uuid.uuid4()
    research_b = uuid.uuid4()
    tracker.start_stage(research_a, "planning")
    tracker.end_stage(research_a, "planning")
    tracker.start_stage(research_b, "planning")
    tracker.end_stage(research_b, "planning")

    metrics = tracker.get_metrics(research_a)

    assert len(metrics) == 1
    assert all(m.research_id == research_a for m in metrics)


def test_calculate_time_to_first_result() -> None:
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    metrics = [
        _metric("planning", start, start + timedelta(seconds=5)),
        _metric("search", start + timedelta(seconds=5), start + timedelta(seconds=20)),
    ]

    assert calculate_time_to_first_result(metrics) == pytest.approx(20.0)


def test_calculate_time_to_first_result_no_search() -> None:
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    metrics = [_metric("planning", start, start + timedelta(seconds=5))]

    assert calculate_time_to_first_result(metrics) is None


def test_calculate_time_to_completion() -> None:
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    metrics = [
        _metric("planning", start, start + timedelta(seconds=5)),
        _metric("synthesis", start + timedelta(seconds=5), start + timedelta(seconds=30)),
    ]

    assert calculate_time_to_completion(metrics) == pytest.approx(30.0)


def test_calculate_time_to_completion_empty() -> None:
    assert calculate_time_to_completion([]) == 0.0


def test_calculate_throughput() -> None:
    assert calculate_throughput(10, 60) == pytest.approx(10.0)
    assert calculate_throughput(5, 30) == pytest.approx(10.0)


def test_calculate_throughput_zero_duration() -> None:
    assert calculate_throughput(10, 0) == 0.0


def test_calculate_error_rate() -> None:
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    metrics = [
        _metric("planning", start, start + timedelta(seconds=1), status="success"),
        _metric("search", start, start + timedelta(seconds=1), status="failed"),
        _metric("processing", start, start + timedelta(seconds=1), status="success"),
    ]

    assert calculate_error_rate(metrics) == pytest.approx(1 / 3)


def test_calculate_error_rate_empty() -> None:
    assert calculate_error_rate([]) == 0.0


def test_get_report_contains_all_fields(db: Session) -> None:
    tracker = PerformanceTracker(db)
    research_id = uuid.uuid4()
    tracker.start_stage(research_id, "planning")
    tracker.end_stage(research_id, "planning")
    tracker.start_stage(research_id, "search")
    tracker.end_stage(research_id, "search")

    report = tracker.get_report(research_id, documents_found=8, documents_processed=6)

    assert report.research_id == research_id
    assert report.time_to_first_result is not None
    assert report.time_to_completion >= 0
    assert report.documents_found == 8
    assert report.documents_processed == 6
    assert report.throughput_docs_per_minute >= 0
    assert report.error_rate == 0.0
    assert len(report.stages) == 2
    assert {s.stage for s in report.stages} == {"planning", "search"}
    assert all(s.duration_seconds >= 0 for s in report.stages)


def test_get_report_empty_research(db: Session) -> None:
    report = PerformanceTracker(db).get_report(uuid.uuid4())

    assert report.time_to_first_result is None
    assert report.time_to_completion == 0.0
    assert report.documents_found == 0
    assert report.documents_processed == 0
    assert report.throughput_docs_per_minute == 0.0
    assert report.error_rate == 0.0
    assert report.stages == []
