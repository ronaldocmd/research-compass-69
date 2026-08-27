"""RDA-058 retrieval query strategy comparison.

Compares how the retrieval query is built affects retrieval quality on the
RDA-057 gold benchmark. The previous pipeline used the EXTRACT task title
alone (often a generic instruction like "Extract key findings from the
selected studies"). This harness measures:

  A) generic task title (simulated)          - the old behaviour
  B) research question                       - the new default
  C) research question + task description    - the new default (question_description)

Run from the backend directory:

    python scripts/evaluation/compare_query_strategies.py
"""

import json
import math
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.embeddings.openai_provider import OpenAIEmbeddingProvider
from app.services.retrieval.retriever import DocumentRetriever
from app.services.retrieval.schemas import IndexedChunk

BENCHMARK_PATH = Path(__file__).resolve().parents[2] / "data" / "benchmarks" / "retrieval_gold_v1.json"
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "evaluation"

# Simulated generic EXTRACT task titles the planner might produce, mapped by
# topic. These are deliberately generic extraction instructions that do not
# carry the research intent.
GENERIC_TASK_TITLES = {
    "systematic_review": "Extract key findings from the selected studies",
    "llm_code": "Extract the main results from the selected studies",
    "lung_cancer": "Extract data on the selected studies",
    "recommendation": "Extract the key metrics from the selected studies",
    "chain_of_thought": "Extract the main findings from the selected studies",
    "embeddings": "Extract the key limitations from the selected studies",
}


def load_benchmark() -> dict:
    return json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))


def build_index(benchmark: dict, provider) -> list[IndexedChunk]:
    index: list[IndexedChunk] = []
    for item in benchmark["corpus"]:
        embedding = provider.embed(item["text"])
        index.append(
            IndexedChunk(
                chunk_id=uuid.uuid5(uuid.NAMESPACE_URL, item["chunk_id"]),
                document_id=uuid.uuid5(uuid.NAMESPACE_URL, item["document_id"]),
                text=item["text"],
                page_number=1,
                section=item["topic"],
                embedding=embedding,
                document_title=item["topic"],
            )
        )
    return index


def ndcg_at_k(ranked_grades, ideal_grades, k):
    def dcg(rel):
        rel = rel[:k]
        if not rel:
            return 0.0
        return rel[0] + sum(r / math.log2(i + 1) for i, r in enumerate(rel[1:], start=2))
    d = dcg(ranked_grades)
    i = dcg(sorted(ideal_grades, reverse=True))
    return d / i if i > 0 else 0.0


def evaluate(retriever, query, chunk_id_map):
    relevant = query["relevant"]
    relevant_ids = {chunk_id_map[cid] for cid in relevant}
    grades = {chunk_id_map[cid]: g for cid, g in relevant.items()}
    res = retriever.retrieve(query["question"])
    ranked = res.chunks
    ranked_ids = [c.chunk_id for c in ranked]
    ranked_grades = [grades.get(cid, 0) for cid in ranked_ids]
    total = len(relevant_ids)
    rel_in_top5 = sum(1 for cid in ranked_ids[:5] if cid in relevant_ids)
    mrr = 0.0
    for i, cid in enumerate(ranked_ids, start=1):
        if cid in relevant_ids:
            mrr = 1.0 / i
            break
    return {
        "R@5": round(rel_in_top5 / total, 4) if total else 0.0,
        "Hit@5": 1 if rel_in_top5 > 0 else 0,
        "MRR": round(mrr, 4),
        "NDCG@5": round(ndcg_at_k(ranked_grades, sorted(grades.values(), reverse=True), 5), 4),
    }


def main() -> None:
    benchmark = load_benchmark()
    provider = OpenAIEmbeddingProvider()
    index = build_index(benchmark, provider)
    chunk_id_map = {item["chunk_id"]: c.chunk_id for item, c in zip(benchmark["corpus"], index)}

    # Map each query to its topic via the relevant chunk ids.
    topic_by_chunk = {item["chunk_id"]: item["topic"] for item in benchmark["corpus"]}

    strategies = {"A_task_title": [], "B_question": [], "C_question_description": []}
    per_query = []

    for q in benchmark["queries"]:
        relevant_chunks = list(q["relevant"].keys())
        topic = topic_by_chunk.get(relevant_chunks[0], "systematic_review") if relevant_chunks else "systematic_review"
        generic_title = GENERIC_TASK_TITLES.get(topic, "Extract key findings from the selected studies")
        description = f"Extract and summarize the evidence relevant to: {q['question']}"

        queries = {
            "A_task_title": generic_title,
            "B_question": q["question"],
            "C_question_description": f"{q['question']} {description}",
        }
        row = {"query_id": q["query_id"], "topic": topic}
        for name, query in queries.items():
            retriever = DocumentRetriever(provider=provider, index=index, top_k=5, min_score=0.5)
            m = evaluate(retriever, {**q, "question": query}, chunk_id_map)
            strategies[name].append(m)
            row[name] = m
        per_query.append(row)

    def avg(rows, key):
        return round(sum(r[key] for r in rows) / len(rows), 4)

    report = {
        "audit": "RDA-058 query strategy comparison",
        "timestamp": datetime.now(UTC).isoformat(),
        "commit": _git_commit(),
        "embedding_model": provider.model,
        "min_score": 0.5,
        "top_k": 5,
        "aggregates": {
            name: {
                "R@5": avg(rows, "R@5"),
                "Hit@5": avg(rows, "Hit@5"),
                "MRR": avg(rows, "MRR"),
                "NDCG@5": avg(rows, "NDCG@5"),
            }
            for name, rows in strategies.items()
        },
        "per_query": per_query,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"query_strategy_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== RDA-058 QUERY STRATEGY COMPARISON ===")
    for name, rows in strategies.items():
        print(f"{name}: R@5={avg(rows,'R@5')} Hit@5={avg(rows,'Hit@5')} MRR={avg(rows,'MRR')} NDCG@5={avg(rows,'NDCG@5')}")
    print("Report:", out)


def _git_commit() -> str:
    try:
        import subprocess
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2]).decode().strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    main()
