"""RDA-057 retrieval audit harness.

Loads the controlled gold benchmark (retrieval_gold_v1), embeds the corpus
with the real embedding provider, runs the real DocumentRetriever for every
query, and computes retrieval metrics (P@K, R@K, Hit, MRR, NDCG), score
distributions, threshold sweeps and top-k sweeps.

Reproducible: model/provider/params and the commit are recorded in the JSON
report. Run from the backend directory:

    python scripts/evaluation/run_retrieval_audit.py
"""

import json
import math
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import settings
from app.services.embeddings.openai_provider import OpenAIEmbeddingProvider
from app.services.retrieval.retriever import DocumentRetriever
from app.services.retrieval.schemas import IndexedChunk

BENCHMARK_PATH = Path(__file__).resolve().parents[2] / "data" / "benchmarks" / "retrieval_gold_v1.json"
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "evaluation"


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


def dcg_at_k(rel: list[float], k: int) -> float:
    rel = rel[:k]
    if not rel:
        return 0.0
    return rel[0] + sum(r / math.log2(i + 1) for i, r in enumerate(rel[1:], start=2))


def ndcg_at_k(ranked_grades: list[float], ideal_grades: list[float], k: int) -> float:
    dcg = dcg_at_k(ranked_grades, k)
    idcg = dcg_at_k(sorted(ideal_grades, reverse=True), k)
    return dcg / idcg if idcg > 0 else 0.0


def evaluate_query(retriever, query: dict, index: list[IndexedChunk], chunk_id_map: dict) -> dict:
    relevant = query["relevant"]
    relevant_ids = {chunk_id_map[cid] for cid in relevant}
    grades = {chunk_id_map[cid]: g for cid, g in relevant.items()}

    result = retriever.retrieve(query["question"], top_k=20)
    ranked = result.chunks
    ranked_ids = [c.chunk_id for c in ranked]
    ranked_grades = [grades.get(cid, 0) for cid in ranked_ids]

    total_relevant = len(relevant_ids)
    ideal_grades = sorted(grades.values(), reverse=True)

    metrics: dict = {"query_id": query["query_id"], "difficulty": query["difficulty"],
                     "adversarial": query["adversarial"], "question": query["question"]}
    for k in (1, 3, 5, 10):
        top = ranked_ids[:k]
        rel_in_top = sum(1 for cid in top if cid in relevant_ids)
        metrics[f"P@{k}"] = round(rel_in_top / k, 4) if k else 0.0
        metrics[f"R@{k}"] = round(rel_in_top / total_relevant, 4) if total_relevant else 0.0
        metrics[f"Hit@{k}"] = 1 if rel_in_top > 0 else 0
    for k in (5, 10):
        metrics[f"NDCG@{k}"] = round(ndcg_at_k(ranked_grades, ideal_grades, k), 4)

    # MRR: reciprocal rank of first relevant item.
    mrr = 0.0
    for i, cid in enumerate(ranked_ids, start=1):
        if cid in relevant_ids:
            mrr = 1.0 / i
            break
    metrics["MRR"] = round(mrr, 4)

    # Score distribution for relevant vs irrelevant retrieved chunks.
    rel_scores = [c.score for c in ranked if c.chunk_id in relevant_ids]
    irr_scores = [c.score for c in ranked if c.chunk_id not in relevant_ids]
    metrics["relevant_scores"] = [round(s, 4) for s in rel_scores]
    metrics["irrelevant_scores"] = [round(s, 4) for s in irr_scores]
    metrics["ranked_chunk_ids"] = [str(cid) for cid in ranked_ids]
    metrics["total_found"] = result.total_found
    return metrics


def full_score_separation(provider, queries, index, chunk_id_map) -> dict:
    """Score every corpus chunk for every query (min_score=0) and compare the
    distribution of relevant vs irrelevant chunks. This is the FASE 5 signal:
    whether a simple threshold can separate relevant from irrelevant content."""
    retriever = DocumentRetriever(provider=provider, index=index, top_k=len(index), min_score=0.0)
    all_rel: list[float] = []
    all_irr: list[float] = []
    per_query = []
    for q in queries:
        relevant = {chunk_id_map[cid] for cid in q["relevant"]}
        res = retriever.retrieve(q["question"])
        rel_scores = [c.score for c in res.chunks if c.chunk_id in relevant]
        irr_scores = [c.score for c in res.chunks if c.chunk_id not in relevant]
        all_rel.extend(rel_scores)
        all_irr.extend(irr_scores)
        per_query.append({
            "query_id": q["query_id"],
            "relevant_scores": [round(s, 4) for s in rel_scores],
            "irrelevant_scores": [round(s, 4) for s in irr_scores],
        })

    def stats(vals):
        if not vals:
            return {"count": 0, "mean": None, "min": None, "max": None, "p25": None, "p50": None, "p75": None}
        s = sorted(vals)
        n = len(s)
        def pct(p):
            return s[min(n - 1, int(p * n))]
        return {
            "count": n,
            "mean": round(sum(s) / n, 4),
            "min": round(s[0], 4),
            "max": round(s[-1], 4),
            "p25": round(pct(0.25), 4),
            "p50": round(pct(0.50), 4),
            "p75": round(pct(0.75), 4),
        }

    return {
        "relevant": stats(all_rel),
        "irrelevant": stats(all_irr),
        "per_query": per_query,
    }


def threshold_sweep(retriever, queries, index, chunk_id_map) -> list[dict]:
    rows = []
    for thr in (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80):
        r = DocumentRetriever(provider=retriever._provider, index=index, top_k=5, min_score=thr)
        tp = fp = fn = 0
        for q in queries:
            relevant = {chunk_id_map[cid] for cid in q["relevant"]}
            res = r.retrieve(q["question"])
            retrieved = {c.chunk_id for c in res.chunks}
            tp += len(retrieved & relevant)
            fp += len(retrieved - relevant)
            fn += len(relevant - retrieved)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        rows.append({
            "threshold": thr, "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(2 * precision * recall / (precision + recall), 4) if (precision + recall) else 0.0,
        })
    return rows


def topk_sweep(retriever, queries, index, chunk_id_map) -> list[dict]:
    rows = []
    for k in (3, 5, 10, 20):
        r = DocumentRetriever(provider=retriever._provider, index=index, top_k=k, min_score=0.0)
        tp = fp = fn = 0
        for q in queries:
            relevant = {chunk_id_map[cid] for cid in q["relevant"]}
            res = r.retrieve(q["question"])
            retrieved = {c.chunk_id for c in res.chunks}
            tp += len(retrieved & relevant)
            fp += len(retrieved - relevant)
            fn += len(relevant - retrieved)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        rows.append({
            "top_k": k, "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(2 * precision * recall / (precision + recall), 4) if (precision + recall) else 0.0,
        })
    return rows


def main() -> None:
    benchmark = load_benchmark()
    provider = OpenAIEmbeddingProvider()
    index = build_index(benchmark, provider)
    chunk_id_map = {item["chunk_id"]: c.chunk_id for item, c in zip(benchmark["corpus"], index)}

    retriever = DocumentRetriever(provider=provider, index=index, top_k=5, min_score=settings.RETRIEVAL_MIN_SCORE)

    results = [evaluate_query(retriever, q, index, chunk_id_map) for q in benchmark["queries"]]

    # Aggregates over all queries.
    def avg(key):
        vals = [r[key] for r in results]
        return round(sum(vals) / len(vals), 4)

    aggregates = {
        "P@1": avg("P@1"), "P@3": avg("P@3"), "P@5": avg("P@5"), "P@10": avg("P@10"),
        "R@3": avg("R@3"), "R@5": avg("R@5"), "R@10": avg("R@10"),
        "Hit@5": avg("Hit@5"), "Hit@10": avg("Hit@10"),
        "MRR": avg("MRR"), "NDCG@5": avg("NDCG@5"), "NDCG@10": avg("NDCG@10"),
    }

    # Score separation over the FULL corpus (min_score=0), not just retrieved.
    score_separation = full_score_separation(provider, benchmark["queries"], index, chunk_id_map)

    report = {
        "audit": "RDA-057 retrieval",
        "timestamp": datetime.now(UTC).isoformat(),
        "commit": _git_commit(),
        "embedding_model": provider.model,
        "embedding_dimension": provider.dimension,
        "retriever_top_k": settings.RETRIEVAL_TOP_K,
        "retriever_min_score": settings.RETRIEVAL_MIN_SCORE,
        "corpus_size": len(index),
        "query_count": len(results),
        "aggregates": aggregates,
        "score_separation": score_separation,
        "threshold_sweep": threshold_sweep(retriever, benchmark["queries"], index, chunk_id_map),
        "topk_sweep": topk_sweep(retriever, benchmark["queries"], index, chunk_id_map),
        "per_query": results,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"retrieval_audit_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== RDA-057 RETRIEVAL AUDIT ===")
    print("Aggregates:", json.dumps(aggregates, indent=2))
    print("Score separation (full corpus):")
    print("  relevant:", json.dumps(score_separation["relevant"]))
    print("  irrelevant:", json.dumps(score_separation["irrelevant"]))
    print("Threshold sweep:")
    for row in report["threshold_sweep"]:
        print(f"  thr={row['threshold']} P={row['precision']} R={row['recall']} F1={row['f1']} (tp={row['tp']} fp={row['fp']} fn={row['fn']})")
    print("Top-k sweep:")
    for row in report["topk_sweep"]:
        print(f"  k={row['top_k']} P={row['precision']} R={row['recall']} F1={row['f1']}")
    print("Per-query:")
    for r in results:
        print(f"  {r['query_id']} [{r['difficulty']}/{r['adversarial']}] P@5={r['P@5']} R@5={r['R@5']} MRR={r['MRR']} NDCG@5={r['NDCG@5']} rel_scores={r['relevant_scores']} irr_scores={r['irrelevant_scores']}")
    print("Report:", out)


def _git_commit() -> str:
    try:
        import subprocess
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2]).decode().strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    main()
