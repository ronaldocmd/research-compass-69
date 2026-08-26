"""PerformanceTracker: per-stage timing and metrics for research runs (RDA-051).

Each workflow stage is recorded as a ``PerformanceMetric`` row (started_at,
completed_at, duration, status). Metrics are derived from those rows:
time to first result, time to completion, throughput and error rate. The
tracker only measures — it never optimizes; identifying bottlenecks is a
follow-up step driven by the data.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.performance_metric import PerformanceMetric
from app.schemas.performance import PerformanceReport, StageMetric


def calculate_time_to_first_result(
    metrics: list[PerformanceMetric],
) -> float | None:
    """Seconds from the earliest stage start to the search stage completion.

    Returns None when there is no completed search stage.
    """
    search_stage = next((m for m in metrics if m.stage == "search"), None)
    if search_stage is None or search_stage.completed_at is None:
        return None
    start = min(m.started_at for m in metrics)
    return (search_stage.completed_at - start).total_seconds()


def calculate_time_to_completion(metrics: list[PerformanceMetric]) -> float:
    """Seconds from the earliest stage start to the latest stage completion."""
    if not metrics:
        return 0.0
    start = min(m.started_at for m in metrics)
    ends = [m.completed_at for m in metrics if m.completed_at is not None]
    end = max(ends) if ends else start
    return (end - start).total_seconds()


def calculate_throughput(docs_processed: int, duration_seconds: float) -> float:
    """Documents processed per minute."""
    if duration_seconds == 0:
        return 0.0
    return (docs_processed / duration_seconds) * 60


def calculate_error_rate(metrics: list[PerformanceMetric]) -> float:
    """Fraction of stages that failed (0..1)."""
    if not metrics:
        return 0.0
    failed = sum(1 for m in metrics if m.status == "failed")
    return failed / len(metrics)


class PerformanceTracker:
    """Persists stage timing and builds a PerformanceReport per research."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def start_stage(self, research_id: uuid.UUID, stage: str) -> PerformanceMetric:
        """Open a stage metric (started_at now, not yet completed)."""
        metric = PerformanceMetric(
            research_id=research_id,
            stage=stage,
            started_at=datetime.now(UTC),
            status="success",
        )
        self.db.add(metric)
        self.db.commit()
        self.db.refresh(metric)
        return metric

    def end_stage(
        self,
        research_id: uuid.UUID,
        stage: str,
        status: str = "success",
        error_message: str | None = None,
    ) -> PerformanceMetric | None:
        """Close the latest open metric for ``research_id``/``stage``.

        Returns None when no open metric exists (e.g. stage never started).
        """
        metric = self._latest_open(research_id, stage)
        if metric is None:
            return None
        metric.completed_at = datetime.now(UTC)
        # SQLite returns naive datetimes; normalize so the subtraction works
        # on both SQLite (naive) and PostgreSQL (timezone-aware).
        started = metric.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        metric.duration_seconds = (metric.completed_at - started).total_seconds()
        metric.status = status
        metric.error_message = error_message
        self.db.commit()
        self.db.refresh(metric)
        return metric

    def get_metrics(self, research_id: uuid.UUID) -> list[PerformanceMetric]:
        stmt = (
            select(PerformanceMetric)
            .where(PerformanceMetric.research_id == research_id)
            .order_by(PerformanceMetric.started_at.asc())
        )
        return list(self.db.execute(stmt).scalars())

    def get_report(
        self,
        research_id: uuid.UUID,
        *,
        documents_found: int = 0,
        documents_processed: int = 0,
    ) -> PerformanceReport:
        """Build the aggregated performance report for a research.

        ``documents_found``/``documents_processed`` are supplied by the caller
        (workflow state / benchmark) since the metrics table tracks stages, not
        document counts.
        """
        metrics = self.get_metrics(research_id)
        time_to_completion = calculate_time_to_completion(metrics)
        return PerformanceReport(
            research_id=research_id,
            time_to_first_result=calculate_time_to_first_result(metrics),
            time_to_completion=time_to_completion,
            documents_found=documents_found,
            documents_processed=documents_processed,
            throughput_docs_per_minute=calculate_throughput(
                documents_processed, time_to_completion
            ),
            error_rate=calculate_error_rate(metrics),
            stages=[
                StageMetric(
                    stage=m.stage,
                    duration_seconds=m.duration_seconds or 0.0,
                    status=m.status,
                )
                for m in metrics
            ],
        )

    def _latest_open(
        self, research_id: uuid.UUID, stage: str
    ) -> PerformanceMetric | None:
        stmt = (
            select(PerformanceMetric)
            .where(
                PerformanceMetric.research_id == research_id,
                PerformanceMetric.stage == stage,
                PerformanceMetric.completed_at.is_(None),
            )
            .order_by(PerformanceMetric.started_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()
