"""RDA-064 live semantic benchmark runner.

Runs the real EvidenceValidator (LLM) against the 70-case semantic gold
benchmark and writes the per-case outcomes plus aggregate metrics to
data/evaluation/semantic_rda064_<run_id>.json.

Usage:
    python -m redteam.live_semantic_benchmark [--runs N] [--output DIR]
"""

import argparse
import json
from pathlib import Path

from app.evaluation.semantic_benchmark import (
    run_semantic_benchmark,
    write_semantic_report,
)


def _print_result(r) -> None:
    m = r.metrics
    print(f"run_id={r.run_id} version={r.version}")
    print(
        f"total={m.total} correct={m.correct} accuracy={m.accuracy} "
        f"precision={m.precision} recall={m.recall} f1={m.f1} "
        f"fpr={m.false_positive_rate} fnr={m.false_negative_rate}"
    )
    print(
        f"dangerous: unsupported->supported={m.unsupported_to_supported} "
        f"contradicted->supported={m.contradicted_to_supported} "
        f"partial->supported={m.partial_to_supported}"
    )
    print("confusion matrix (expected x actual):")
    for exp, row in r.confusion.items():
        print(f"  {exp:20s} " + " ".join(f"{k}={v}" for k, v in row.items()))
    print("per-category:")
    by_cat: dict[str, list] = {}
    for c in r.cases:
        by_cat.setdefault(c["category"], []).append(c)
    for cat, cases in sorted(by_cat.items()):
        ok = sum(1 for c in cases if c["correct"])
        print(f"  {cat:24s} {ok}/{len(cases)}")
    print("misses:")
    for c in r.cases:
        if not c["correct"]:
            print(
                f"  MISS {c['id']} {c['category']:24s} "
                f"expected={c['expected']:20s} actual={c['actual']}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1, help="number of runs")
    parser.add_argument("--output", default="data/evaluation")
    args = parser.parse_args()

    paths: list[Path] = []
    for i in range(args.runs):
        print(f"=== run {i+1}/{args.runs} ===", flush=True)
        r = run_semantic_benchmark(verbose=True)
        _print_result(r)
        path = write_semantic_report(r, args.output)
        paths.append(path)
        print(f"wrote {path}\n")

    if args.runs > 1:
        # Aggregate determinism across runs.
        print("=== determinism across runs ===")
        all_cases = []
        for p in paths:
            data = json.loads(p.read_text(encoding="utf-8"))
            all_cases.append({c["id"]: c["actual"] for c in data["cases"]})
        ids = list(all_cases[0].keys())
        stable = 0
        for cid in ids:
            vals = {r[cid] for r in all_cases}
            if len(vals) == 1:
                stable += 1
        print(f"cases stable across {args.runs} runs: {stable}/{len(ids)}")


if __name__ == "__main__":
    main()
