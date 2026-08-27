"""RDA-057 evidence & claims audit harness.

Runs the REAL ClaimExtractor and EvidenceExtractor (LLM via LiteLLM) on a
controlled set of scenarios to measure whether evidence is grounded in the
source and whether claims are supported. Includes a hallucination test where
chunks directly support, partially support, contradict, or do not contain the
information a query asks about.

Run from the backend directory:

    python scripts/evaluation/run_evidence_audit.py
"""

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.claims.extractor import ClaimExtractor
from app.services.evidence.extractor import EvidenceExtractor
from app.services.evidence.schemas import EvidenceStatus
from app.services.retrieval.schemas import RetrievedChunk

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "evaluation"

SCENARIOS = [
    {
        "id": "s1_direct_support",
        "query": "What is the effect of LLM-based tutoring on student exam scores?",
        "chunks": [
            "A randomized trial of 1,200 students found that LLM-based tutoring improved exam scores by 18% compared to traditional instruction.",
        ],
        "expected": "direct_support",
    },
    {
        "id": "s2_partial_support",
        "query": "What is the effect of LLM-based tutoring on student exam scores?",
        "chunks": [
            "Several studies report that AI tutoring tools are associated with improved student engagement, though effect sizes vary widely across contexts.",
        ],
        "expected": "partial_support",
    },
    {
        "id": "s3_contradiction",
        "query": "What is the effect of LLM-based tutoring on student exam scores?",
        "chunks": [
            "A meta-analysis found that LLM-based tutoring had no significant effect on student exam scores, with a pooled effect size near zero.",
        ],
        "expected": "contradiction",
    },
    {
        "id": "s4_absent_info",
        "query": "What is the effect of LLM-based tutoring on student exam scores?",
        "chunks": [
            "The study examined the impact of classroom size on student attention spans in primary schools.",
        ],
        "expected": "absent_info",
    },
]


def make_chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid5(uuid.NAMESPACE_URL, text),
        document_id=uuid.uuid5(uuid.NAMESPACE_URL, "doc-" + text[:20]),
        text=text,
        page_number=1,
        section="Results",
        score=0.8,
        document_title="Controlled scenario",
    )


def run_scenario(scenario: dict, claim_extractor, evidence_extractor) -> dict:
    chunks = [make_chunk(t) for t in scenario["chunks"]]
    out = {
        "id": scenario["id"],
        "query": scenario["query"],
        "expected": scenario["expected"],
        "claims": [],
    }
    try:
        claim_result = claim_extractor.extract(chunks, scenario["query"])
    except Exception as exc:  # noqa: BLE001
        out["claim_extraction_error"] = str(exc)
        return out

    for claim in claim_result.claims:
        claim_entry = {
            "claim_text": claim.text,
            "chunk_ids": [str(c) for c in claim.chunk_ids],
            "document_id": str(claim.document_id),
            "evidence": [],
        }
        try:
            ev_result = evidence_extractor.extract(claim, chunks)
        except Exception as exc:  # noqa: BLE001
            claim_entry["evidence_error"] = str(exc)
            out["claims"].append(claim_entry)
            continue
        claim_entry["final_status"] = ev_result.final_status.value
        for ev in ev_result.evidence:
            claim_entry["evidence"].append({
                "status": ev.status.value,
                "text": ev.text,
                "chunk_id": str(ev.chunk_id) if ev.chunk_id else None,
                "document_id": str(ev.document_id) if ev.document_id else None,
                "page_number": ev.page_number,
            })
        out["claims"].append(claim_entry)
    return out


def main() -> None:
    claim_extractor = ClaimExtractor()
    evidence_extractor = EvidenceExtractor()
    results = [run_scenario(s, claim_extractor, evidence_extractor) for s in SCENARIOS]

    report = {
        "audit": "RDA-057 evidence & claims",
        "timestamp": datetime.now(UTC).isoformat(),
        "commit": _git_commit(),
        "llm_model": claim_extractor._llm.model,
        "scenarios": results,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"evidence_audit_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== RDA-057 EVIDENCE & CLAIMS AUDIT ===")
    for r in results:
        print(f"\n[{r['id']}] expected={r['expected']}")
        if "claim_extraction_error" in r:
            print("  claim extraction ERROR:", r["claim_extraction_error"])
            continue
        if not r["claims"]:
            print("  -> 0 claims extracted")
            continue
        for c in r["claims"]:
            print(f"  CLAIM: {c['claim_text'][:90]}")
            print(f"    chunk_ids={c['chunk_ids']} final_status={c.get('final_status')}")
            for ev in c["evidence"]:
                print(f"    EVIDENCE status={ev['status']} chunk={ev['chunk_id']} text={ev['text']}")
    print("\nReport:", out)


def _git_commit() -> str:
    try:
        import subprocess
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2]).decode().strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    main()
