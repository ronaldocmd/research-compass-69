"""RDA-059 threshold sweep for cross-lingual (PT->EN) retrieval.

Measures precision/recall/F1 at various thresholds for PT queries against
EN documents, and compares with EN->EN, to find the best operating point for
the real production scenario (Portuguese research question, English academic
documents). Also reports the full score distribution of relevant vs
irrelevant chunks for PT queries.
"""

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.embeddings.openai_provider import OpenAIEmbeddingProvider
from app.services.retrieval.retriever import DocumentRetriever, cosine_similarity
from app.services.retrieval.schemas import IndexedChunk

BENCHMARK_PATH = Path(__file__).resolve().parents[2] / "data" / "benchmarks" / "retrieval_crosslingual_v1.json"
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


def main() -> None:
    benchmark = load_benchmark()
    provider = OpenAIEmbeddingProvider()
    index = build_index(benchmark, provider)
    chunk_id_map = {item["chunk_id"]: c.chunk_id for item, c in zip(benchmark["corpus"], index)}

    # Precompute all query embeddings (PT and EN) and all chunk embeddings.
    queries = []
    for pair in benchmark["query_pairs"]:
        relevant_ids = {chunk_id_map[cid] for cid in pair["relevant"]}
        queries.append({"pair_id": pair["pair_id"], "lang": "PT", "text": pair["pt"], "relevant": relevant_ids})
        queries.append({"pair_id": pair["pair_id"], "lang": "EN", "text": pair["en"], "relevant": relevant_ids})

    # For each query, compute raw score against every chunk.
    scored_queries = []
    for q in queries:
        q_emb = provider.embed(q["text"])
        scores = [(cosine_similarity(q_emb, c.embedding), c.chunk_id) for c in index]
        scored_queries.append({**q, "scores": scores})

    thresholds = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
    results = {"PT": [], "EN": []}
    for thr in thresholds:
        for lang in ("PT", "EN"):
            tp = fp = fn = 0
            for q in scored_queries:
                if q["lang"] != lang:
                    continue
                retrieved = {cid for s, cid in q["scores"] if s >= thr}
                relevant = q["relevant"]
                tp += len(retrieved & relevant)
                fp += len(retrieved - relevant)
                fn += len(relevant - retrieved)
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
            results[lang].append({
                "threshold": thr, "tp": tp, "fp": fp, "fn": fn,
                "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            })

    # Score distribution of relevant vs irrelevant for PT queries.
    pt_rel, pt_irr = [], []
    for q in scored_queries:
        if q["lang"] != "PT":
            continue
        for s, cid in q["scores"]:
            if cid in q["relevant"]:
                pt_rel.append(s)
            else:
                pt_irr.append(s)

    def stats(vals):
        if not vals:
            return {"count": 0, "mean": None, "min": None, "max": None}
        s = sorted(vals)
        return {
            "count": len(s), "mean": round(sum(s) / len(s), 4),
            "min": round(s[0], 4), "max": round(s[-1], 4),
            "p25": round(s[int(0.25 * len(s))], 4), "p50": round(s[int(0.5 * len(s))], 4),
            "p75": round(s[int(0.75 * len(s))], 4),
        }

    report = {
        "audit": "RDA-059 threshold sweep cross-lingual",
        "timestamp": datetime.now(UTC).isoformat(),
        "commit": _git_commit(),
        "embedding_model": provider.model,
        "sweep": results,
        "pt_score_distribution": {"relevant": stats(pt_rel), "irrelevant": stats(pt_irr)},
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"crosslingual_sweep_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== RDA-059 THRESHOLD SWEEP (PT->EN vs EN->EN) ===")
    print("PT queries (cross-lingual):")
    for r in results["PT"]:
        print(f"  thr={r['threshold']} P={r['precision']} R={r['recall']} F1={r['f1']} (tp={r['tp']} fp={r['fp']} fn={r['fn']})")
    print("EN queries (same-language):")
    for r in results["EN"]:
        print(f"  thr={r['threshold']} P={r['precision']} R={r['recall']} F1={r['f1']} (tp={r['tp']} fp={r['fp']} fn={r['fn']})")
    print("PT score distribution:")
    print("  relevant:", json.dumps(report["pt_score_distribution"]["relevant"]))
    print("  irrelevant:", json.dumps(report["pt_score_distribution"]["irrelevant"]))
    print("Report:", out)


def _git_commit() -> str:
    try:
        import subprocess
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2]).decode().strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    main()
