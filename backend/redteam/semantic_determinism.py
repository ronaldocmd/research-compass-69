"""RDA-064 LLM determinism check.

Runs a representative subset of the semantic benchmark 3x through the real
EvidenceValidator and measures how often the LLM returns the same status for
the same claim/evidence pair across runs.

Usage:
    python -m redteam.semantic_determinism
"""

import json
from collections import Counter

from app.evaluation.semantic_benchmark import load_semantic_benchmark
from app.services.validation.validator import EvidenceValidator

# Representative subset spanning the categories most relevant to calibration.
SUBSET = [
    "A01", "B01", "C01", "C02", "C05", "C07", "D01", "D04",
    "E01", "E04", "F02", "G01", "G02", "H01", "J01",
]
RUNS = 3


def main() -> None:
    dataset = load_semantic_benchmark()
    by_id = {c.id: c for c in dataset.cases}
    validator = EvidenceValidator()
    results: dict[str, list[str]] = {}
    for cid in SUBSET:
        case = by_id[cid]
        outcomes = []
        for _ in range(RUNS):
            claim = case.claim
            evidence = case.evidence
            from app.evaluation.semantic_benchmark import _claim, _evidence

            c = _claim(claim)
            e = _evidence(c, evidence)
            try:
                r = validator.validate(c, e)
                outcomes.append(r.status.value)
            except Exception as exc:  # noqa: BLE001
                outcomes.append(f"ERROR:{type(exc).__name__}")
        results[cid] = outcomes
        print(f"{cid} {case.category:20s} expected={case.expected.value:20s} "
              f"runs={outcomes}")

    stable = sum(1 for v in results.values() if len(set(v)) == 1)
    print(f"\nstable across {RUNS} runs: {stable}/{len(SUBSET)}")
    # Per-case distribution
    for cid, vals in results.items():
        dist = dict(Counter(vals))
        print(f"  {cid}: {dist}")

    with open("redteam/semantic_determinism_results.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
