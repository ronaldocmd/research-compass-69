"""Reproducible performance benchmark for the RDA (RDA-051).

For each question in a benchmark dataset, runs the research workflow with a
DB-backed PerformanceTracker, derives document counts from the returned
workflow state, and writes a consolidated JSON report. Results are stored so
versions can be compared over time.

The benchmark needs a configured orchestrator (with real services) and a DB
session; the CLI validates the dataset and explains what is required.
"""

import argparse
import asyncio
import json
import sys
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluation.benchmark import load_benchmark
from app.schemas.performance import PerformanceReport
from app.services.orchestration.orchestrator import ResearchOrchestrator
from app.services.performance.tracker import PerformanceTracker


async def run_performance_benchmark(
    benchmark_version: str = "v1.0",
    orchestrator: ResearchOrchestrator | None = None,
    db=None,
    output_dir: str | Path = "data/performance",
) -> list[Path]:
    """Run the workflow for each benchmark question and write JSON reports.

    ``orchestrator`` must be a configured ResearchOrchestrator (with real
    services) and ``db`` a SQLAlchemy Session. Each run records per-stage
    timing through a PerformanceTracker and the report is persisted.
    """
    dataset = load_benchmark(benchmark_version)
    if orchestrator is None or db is None:
        raise ValueError("a configured orchestrator and DB session are required")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    reports: list[Path] = []
    for question in dataset.questions:
        research_id = uuid.uuid5(uuid.NAMESPACE_URL, f"benchmark:{question.id}")
        tracker = PerformanceTracker(db)
        run_orchestrator = ResearchOrchestrator(performance_tracker=tracker)
        state = await run_orchestrator.run(research_id)
        report = tracker.get_report(
            research_id,
            documents_found=len(state.search_results),
            documents_processed=len(state.processed_document_ids),
        )
        path = output / f"{question.id}.json"
        path.write_text(
            json.dumps(
                report.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        reports.append(path)
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RDA performance benchmark")
    parser.add_argument("--benchmark-version", default="v1.0")
    parser.add_argument("--output-dir", default="data/performance")
    args = parser.parse_args()

    dataset = load_benchmark(args.benchmark_version)
    print(
        f"Benchmark {dataset.version} validado ({len(dataset.questions)} casos). "
        "Nenhuma execução foi feita: o benchmark requer um ResearchOrchestrator "
        "configurado (com serviços reais) e uma sessão de banco."
    )


if __name__ == "__main__":
    asyncio.run(asyncio.to_thread(main))
