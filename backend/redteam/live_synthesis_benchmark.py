"""RDA-065 live synthesis benchmark runner.

Runs the real synthesis prompt (LLM) against the 54-case synthesis gold
benchmark and writes the per-case outcomes plus aggregate metrics to
data/evaluation/synthesis_rda065_<run_id>.json.

Usage:
    python -m redteam.live_synthesis_benchmark [--model MODEL] [--output DIR]
"""

import argparse

from app.evaluation.synthesis_benchmark import (
    run_synthesis_benchmark,
    write_synthesis_report,
)
from app.services.llm.openai_provider import OpenAILLMProvider


def _print_result(r) -> None:
    m = r.metrics
    print(f"run_id={r.run_id} version={r.version} prompt_mode={r.prompt_mode}")
    print(
        f"total={m.total} correct={m.correct} accuracy={m.accuracy}"
    )
    print("per-category:")
    for cat, counts in sorted(m.per_category.items()):
        print(f"  {cat:20s} {counts['correct']}/{counts['total']}")
    print("failures:")
    for c in r.cases:
        if not c["pass"]:
            print(f"  FAIL {c['id']} {c['category']:20s} | {c['reason'][:110]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt-4o-mini-openai",
                        help="LLM model to use (default gpt-4o-mini-openai; the "
                             "default gpt-4o-mini group is currently failing on "
                             "the proxy)")
    parser.add_argument("--mode", default="claims_only",
                        choices=["claims_only", "hardened"],
                        help="prompt variant to test")
    parser.add_argument("--output", default="data/evaluation")
    args = parser.parse_args()

    llm = OpenAILLMProvider(model=args.model)
    print(f"=== RDA-065 synthesis benchmark (mode={args.mode}, model={args.model}) ===", flush=True)
    r = run_synthesis_benchmark(llm=llm, verbose=True, prompt_mode=args.mode)
    _print_result(r)
    path = write_synthesis_report(r, args.output)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
