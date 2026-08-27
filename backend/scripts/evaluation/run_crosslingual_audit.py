"""RDA-059 cross-lingual retrieval audit harness.

Measures why a Portuguese research question underperforms when the relevant
documents are in English. For every PT/EN query pair it:

  1. embeds the query with the real provider;
  2. computes the RAW cosine score against every relevant chunk (no threshold);
  3. runs the real DocumentRetriever at the configured threshold (0.5) and
     reports how many relevant chunks survive;
  4. builds the experimental matrix (PT->PT, PT->EN, EN->EN, EN->PT) using
     the relevant chunks' language.

Run from the backend directory:

    python scripts/evaluation/run_crosslingual_audit.py
"""

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import settings
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
    lang_by_chunk = {item["chunk_id"]: item["lang"] for item in benchmark["corpus"]}

    retriever = DocumentRetriever(provider=provider, index=index, top_k=20, min_score=settings.RETRIEVAL_MIN_SCORE)

    per_pair = []
    # Matrix accumulators: (query_lang, doc_lang) -> list of raw scores.
    matrix: dict[str, list[float]] = {}
    # Threshold survival: (query_lang, doc_lang) -> [retrieved, total_relevant]
    survival: dict[str, list[int]] = {}

    for pair in benchmark["query_pairs"]:
        row = {"pair_id": pair["pair_id"], "topic": pair["topic"]}
        for qlang, qtext in (("PT", pair["pt"]), ("EN", pair["en"])):
            relevant = pair["relevant"]
            relevant_ids = {chunk_id_map[cid] for cid in relevant}
            # Raw scores against every relevant chunk (no threshold).
            q_emb = provider.embed(qtext)
            raw_scores = {}
            for cid, grade in relevant.items():
                chunk = index[[c.chunk_id for c in index].index(chunk_id_map[cid])]
                raw_scores[cid] = round(cosine_similarity(q_emb, chunk.embedding), 4)
            # Threshold survival via the real retriever.
            res = retriever.retrieve(qtext)
            retrieved_ids = {c.chunk_id for c in res.chunks}
            hit = sum(1 for cid in relevant_ids if cid in retrieved_ids)
            total = len(relevant_ids)

            row[f"{qlang}_raw_scores"] = raw_scores
            row[f"{qlang}_retrieved"] = hit
            row[f"{qlang}_total"] = total

            # Matrix: for each relevant chunk, record (query_lang, doc_lang).
            for cid, grade in relevant.items():
                doc_lang = lang_by_chunk[cid]
                key = f"{qlang}->{doc_lang}"
                matrix.setdefault(key, []).append(raw_scores[cid])
                survival.setdefault(key, [0, 0])
                survival[key][1] += 1
                if chunk_id_map[cid] in retrieved_ids:
                    survival[key][0] += 1
        per_pair.append(row)

    def stats(vals):
        if not vals:
            return {"count": 0, "mean": None, "min": None, "max": None}
        return {
            "count": len(vals),
            "mean": round(sum(vals) / len(vals), 4),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
        }

    matrix_report = {}
    for key, vals in matrix.items():
        s = stats(vals)
        surv = survival[key]
        s["retrieved_at_threshold"] = surv[0]
        s["total_relevant"] = surv[1]
        s["recall_at_threshold"] = round(surv[0] / surv[1], 4) if surv[1] else None
        matrix_report[key] = s

    report = {
        "audit": "RDA-059 cross-lingual retrieval",
        "timestamp": datetime.now(UTC).isoformat(),
        "commit": _git_commit(),
        "embedding_model": provider.model,
        "embedding_dimension": provider.dimension,
        "threshold": settings.RETRIEVAL_MIN_SCORE,
        "top_k": 20,
        "matrix": matrix_report,
        "per_pair": per_pair,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"crosslingual_audit_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== RDA-059 CROSS-LINGUAL AUDIT ===")
    print("Embedding model:", provider.model, "dim:", provider.dimension, "threshold:", settings.RETRIEVAL_MIN_SCORE)
    print("\nExperimental matrix (raw cosine scores, no threshold):")
    for key, s in matrix_report.items():
        print(f"  {key:8s} n={s['count']:2d} mean={s['mean']} min={s['min']} max={s['max']} | recall@thr={s['recall_at_threshold']} ({s['retrieved_at_threshold']}/{s['total_relevant']})")
    print("\nPer pair (raw scores of relevant chunks):")
    for r in per_pair:
        print(f"  {r['pair_id']} [{r['topic']}]")
        print(f"    PT: retrieved={r['PT_retrieved']}/{r['PT_total']} raw={r['PT_raw_scores']}")
        print(f"    EN: retrieved={r['EN_retrieved']}/{r['EN_total']} raw={r['EN_raw_scores']}")
    print("\nReport:", out)


def _git_commit() -> str:
    try:
        import subprocess
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2]).decode().strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    main()
