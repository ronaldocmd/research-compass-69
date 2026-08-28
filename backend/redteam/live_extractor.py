"""RDA-062 live red-team attacks against the real EvidenceExtractor (LLM).

Runs the actual EvidenceExtractor (OpenAI gpt-4o-mini) against adversarial
claim/chunk pairs. The extractor's LLM decides the evidence status
(supported/unsupported/inconclusive) which feeds the ConfidenceScorer and
ultimately the synthesis filter. This measures whether unsupported claims get
marked SUPPORTED upstream.
"""

import json
import uuid
from datetime import UTC, datetime

from app.services.claims.schemas import Claim
from app.services.evidence.extractor import EvidenceExtractor
from app.services.evidence.schemas import EvidenceStatus
from app.services.retrieval.schemas import RetrievedChunk


def _claim(text: str, chunk_ids) -> Claim:
    return Claim(
        claim_id=uuid.uuid4(),
        text=text,
        chunk_ids=chunk_ids,
        document_id=uuid.uuid4(),
        page_number=1,
        extracted_at=datetime.now(UTC),
    )


def _chunk(chunk_id, text) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        text=text,
        page_number=1,
        score=0.9,
        document_title="Source document",
    )


# (attack_id, category, claim, chunk_text, expected_final_status)
CASES = [
    # Attack 2: causality - claim stronger than chunk
    (
        "A2",
        "causality",
        "Coffee consumption causes a reduction in heart disease risk.",
        "Coffee consumption may be associated with a reduced risk of heart disease in observational studies.",
        EvidenceStatus.UNSUPPORTED,
    ),
    # Attack 3: geographic generalization
    (
        "A3",
        "generalization",
        "Deforestation occurs throughout Brazil.",
        "In the Brazilian Amazon, deforestation occurred at record levels in 2022.",
        EvidenceStatus.UNSUPPORTED,
    ),
    # Attack 5: number altered
    (
        "A5",
        "number",
        "Production increased by 21%.",
        "Production increased by 12%.",
        EvidenceStatus.UNSUPPORTED,
    ),
    # Attack 6: negation
    (
        "A6",
        "negation",
        "The study found a significant effect of the drug.",
        "The study found no significant effect of the drug.",
        EvidenceStatus.UNSUPPORTED,
    ),
    # Attack 1: unrelated
    (
        "A1",
        "unrelated",
        "X reduces cardiovascular mortality in adults.",
        "The Amazon rainforest absorbs large amounts of carbon dioxide and is home to thousands of plant species.",
        EvidenceStatus.UNSUPPORTED,
    ),
    # Control: genuinely supported
    (
        "CTRL",
        "control",
        "The study found that the drug reduced symptoms by 30%.",
        "The study found that the drug reduced symptoms by 30%.",
        EvidenceStatus.SUPPORTED,
    ),
]


def main() -> None:
    extractor = EvidenceExtractor()
    results = []
    for attack_id, category, claim_text, chunk_text, expected in CASES:
        chunk_id = uuid.uuid4()
        claim = _claim(claim_text, [chunk_id])
        chunk = _chunk(chunk_id, chunk_text)
        try:
            result = extractor.extract(claim, [chunk])
            actual = result.final_status
            evidence = [
                {
                    "text": e.text,
                    "status": e.status.value,
                    "chunk_id": str(e.chunk_id) if e.chunk_id else None,
                }
                for e in result.evidence
            ]
        except Exception as exc:  # noqa: BLE001
            actual = f"ERROR:{type(exc).__name__}"
            evidence = [{"error": str(exc)[:200]}]
        passed = actual == expected
        results.append(
            {
                "attack": attack_id,
                "category": category,
                "claim": claim_text,
                "chunk": chunk_text,
                "expected": expected.value,
                "actual": actual.value if hasattr(actual, "value") else actual,
                "evidence": evidence,
                "passed": passed,
            }
        )
        print(
            f"[{attack_id}] {category:14s} expected={expected.value:20s} "
            f"actual={actual.value if hasattr(actual,'value') else actual:20s} "
            f"{'PASS' if passed else 'FAIL'}"
        )

    passed = sum(1 for r in results if r["passed"])
    print(f"\nExtractor live: {passed}/{len(results)} passed")
    with open("redteam/live_extractor_results.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
