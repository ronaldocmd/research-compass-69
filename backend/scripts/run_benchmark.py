"""Command-line entry points for evaluation benchmarks."""

import argparse
import asyncio
import sys
import uuid
from collections.abc import Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluation.benchmark import load_benchmark
from app.evaluation.evidence import EvidenceEvaluationResult, EvidenceEvaluator, write_evaluation_report


async def run_evidence_benchmark(
    benchmark_version: str = "v1.0",
    research_ids: Iterable[uuid.UUID] = (),
    evaluator: EvidenceEvaluator | None = None,
    output_dir: str | Path = "data/evaluation",
) -> list[Path]:
    """Evaluate supplied research executions and write JSON reports.

    The benchmark dataset defines questions; actual claims and evidence must be
    supplied by a loader-backed ``EvidenceEvaluator`` and research IDs.
    """
    load_benchmark(benchmark_version)
    if evaluator is None:
        raise ValueError("an EvidenceEvaluator with data loaders is required")
    reports: list[Path] = []
    for research_id in research_ids:
        result: EvidenceEvaluationResult = evaluator.evaluate(research_id)
        reports.append(write_evaluation_report(result, output_dir))
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RDA evaluation benchmarks")
    parser.add_argument("--evidence", action="store_true", help="run evidence evaluation")
    parser.add_argument("--benchmark-version", default="v1.0")
    parser.add_argument("--research-id", action="append", type=uuid.UUID, default=[])
    args = parser.parse_args()
    if not args.evidence:
        parser.error("choose a benchmark with --evidence")
    if not args.research_id:
        dataset = load_benchmark(args.benchmark_version)
        print(
            f"Benchmark {dataset.version} validado; nenhuma pesquisa foi avaliada "
            "porque não há store de claims/evidências configurado."
        )
        return
    raise SystemExit(
        "Evidence benchmark requires an application-specific EvidenceEvaluator with data loaders"
    )


if __name__ == "__main__":
    asyncio.run(asyncio.to_thread(main))
