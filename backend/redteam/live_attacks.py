"""RDA-062 live red-team attacks against the real EvidenceValidator (LLM).

Runs the actual EvidenceValidator (OpenAI gpt-4o-mini) against adversarial
claim/evidence pairs to measure whether the validator distinguishes genuinely
supported claims from merely plausible, semantically-similar, or accidentally
correct ones.

Each case records the expected status and the validator's actual status.
"""

import json
import uuid
from datetime import UTC, datetime

from app.services.claims.schemas import Claim
from app.services.evidence.schemas import Evidence, EvidenceStatus
from app.services.validation.schemas import ValidationStatus
from app.services.validation.validator import EvidenceValidator


def _claim(text: str) -> Claim:
    return Claim(
        claim_id=uuid.uuid4(),
        text=text,
        chunk_ids=[uuid.uuid4()],
        document_id=uuid.uuid4(),
        page_number=1,
        extracted_at=datetime.now(UTC),
    )


def _evidence(text: str) -> Evidence:
    return Evidence(
        evidence_id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        text=text,
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        page_number=1,
        status=EvidenceStatus.SUPPORTED,
        extracted_at=datetime.now(UTC),
    )


# (attack_id, category, claim, evidence, expected_status)
CASES = [
    # Attack 1: evidence totally unrelated to claim
    (
        "A1",
        "unrelated",
        "X reduces cardiovascular mortality in adults.",
        "The Amazon rainforest absorbs large amounts of carbon dioxide and is home to thousands of plant species.",
        ValidationStatus.UNSUPPORTED,
    ),
    # Attack 2: claim stronger than evidence (causality vs association)
    (
        "A2",
        "causality",
        "Coffee consumption causes a reduction in heart disease risk.",
        "Coffee consumption may be associated with a reduced risk of heart disease in observational studies.",
        ValidationStatus.UNSUPPORTED,
    ),
    # Attack 3: geographic generalization
    (
        "A3",
        "generalization",
        "Deforestation occurs throughout Brazil.",
        "In the Brazilian Amazon, deforestation occurred at record levels in 2022.",
        ValidationStatus.UNSUPPORTED,
    ),
    # Attack 4: temporal generalization
    (
        "A4",
        "generalization",
        "The species continues to decline today.",
        "The species was observed to decline in 2021.",
        ValidationStatus.UNSUPPORTED,
    ),
    # Attack 5: number altered
    (
        "A5",
        "number",
        "Production increased by 21%.",
        "Production increased by 12%.",
        ValidationStatus.UNSUPPORTED,
    ),
    # Attack 6: negation
    (
        "A6",
        "negation",
        "The study found a significant effect of the drug.",
        "The study found no significant effect of the drug.",
        ValidationStatus.UNSUPPORTED,
    ),
    # Attack 9: fabricated evidence (plausible but not in source)
    (
        "A9",
        "fabricated",
        "Vitamin D supplementation reduces the risk of severe respiratory infection.",
        "A randomized trial of 5,000 participants found that daily vitamin D supplementation reduced the incidence of severe respiratory infection by 40% over two years.",
        ValidationStatus.UNSUPPORTED,
    ),
    # Attack 13: evidence similar but contradictory
    (
        "A13",
        "contradiction",
        "The new treatment increases survival rates.",
        "The new treatment does not increase survival rates; patients receiving it showed no improvement over the control group.",
        ValidationStatus.UNSUPPORTED,
    ),
    # Attack 10a: partial evidence, claim fully supported
    (
        "A10a",
        "partial",
        "X increased production by 12%.",
        "X increased production by 12% in 2022, while Y declined by 8%.",
        ValidationStatus.SUPPORTED,
    ),
    # Attack 10b: partial evidence, claim overstates
    (
        "A10b",
        "partial",
        "X increased production by 12% and Y increased by 8%.",
        "X increased production by 12% in 2022, while Y declined by 8%.",
        ValidationStatus.UNSUPPORTED,
    ),
    # Attack 14: multiple evidences combine to support
    (
        "A14",
        "multi_evidence",
        "The bridge was completed in 2023 and cost 2 billion.",
        "The bridge was completed in 2023.",
        ValidationStatus.PARTIALLY_SUPPORTED,
    ),
    # Control: genuinely supported claim
    (
        "CTRL",
        "control",
        "The study found that the drug reduced symptoms by 30%.",
        "The study found that the drug reduced symptoms by 30%.",
        ValidationStatus.SUPPORTED,
    ),
]


def main() -> None:
    validator = EvidenceValidator()
    results = []
    for attack_id, category, claim_text, evidence_text, expected in CASES:
        claim = _claim(claim_text)
        evidence = _evidence(evidence_text)
        try:
            result = validator.validate(claim, evidence)
            actual = result.status
            reasoning = result.reasoning
        except Exception as exc:  # noqa: BLE001
            actual = f"ERROR:{type(exc).__name__}"
            reasoning = str(exc)[:300]
        passed = actual == expected
        results.append(
            {
                "attack": attack_id,
                "category": category,
                "claim": claim_text,
                "evidence": evidence_text,
                "expected": expected.value,
                "actual": actual.value if hasattr(actual, "value") else actual,
                "reasoning": reasoning,
                "passed": passed,
            }
        )
        print(
            f"[{attack_id}] {category:14s} expected={expected.value:20s} "
            f"actual={actual.value if hasattr(actual,'value') else actual:20s} "
            f"{'PASS' if passed else 'FAIL'}"
        )

    passed = sum(1 for r in results if r["passed"])
    print(f"\nValidator live: {passed}/{len(results)} passed")
    with open("redteam/live_validator_results.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
