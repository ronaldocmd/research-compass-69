"""Print the RDA-063 grounding benchmark results."""

from app.evaluation.grounding_benchmark import run_grounding_benchmark


def main() -> None:
    r = run_grounding_benchmark()
    m = r.metrics
    print(f"total {m.total} correct {m.correct} accuracy {m.accuracy}")
    for cat, d in sorted(m.by_category.items()):
        print(f"  {cat:14s} {d['correct']}/{d['total']} accuracy={d['accuracy']}")
    print()
    for c in r.cases:
        if not c["correct"]:
            print(
                f"MISS: {c['id']} {c['category']} expected={c['expected']} "
                f"actual={c['actual']}"
            )


if __name__ == "__main__":
    main()
