"""Print the RDA-062 failure matrix (baseline vs validation gate)."""

from collections import defaultdict

from app.evaluation.redteam import run_redteam


def matrix(use_validation):
    r = run_redteam(use_validation=use_validation)
    bycat = defaultdict(lambda: {"total": 0, "fp": 0, "fn": 0, "ok": 0})
    for c in r.cases:
        b = bycat[c["category"]]
        b["total"] += 1
        if c["correct"]:
            b["ok"] += 1
        elif c["in_summary"] and not c["expected_in_summary"]:
            b["fp"] += 1
        elif not c["in_summary"] and c["expected_in_summary"]:
            b["fn"] += 1
    return r, bycat


for label, uv in [
    ("BASELINE (no validation gate)", False),
    ("WITH VALIDATION GATE", True),
]:
    r, bycat = matrix(uv)
    m = r.metrics
    print(f"=== {label} ===")
    print(
        f"  accuracy={m.accuracy} precision={m.precision} recall={m.recall} "
        f"FPR={m.false_positive_rate} FNR={m.false_negative_rate} "
        f"(FP={m.false_positive}, FN={m.false_negative})"
    )
    for cat in sorted(bycat):
        b = bycat[cat]
        print(f"  {cat:16s} ok={b['ok']}/{b['total']}  FP={b['fp']}  FN={b['fn']}")
    print()
