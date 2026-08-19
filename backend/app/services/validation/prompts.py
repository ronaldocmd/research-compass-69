"""Prompt templates for evidence validation (RDA-028)."""

from app.services.claims.schemas import Claim
from app.services.evidence.schemas import Evidence


def build_validation_prompt(claim: Claim, evidence: Evidence) -> str:
    """Build an independent validation prompt for a claim/evidence pair.

    Deliberately excludes the RDA-026 status so the validator is not biased
    by the earlier extraction's classification: the model only sees the claim
    text and the evidence text.
    """
    return "\n".join(
        [
            "You are validating whether a piece of evidence supports a claim.",
            "",
            f'Given this claim: "{claim.text}"',
            f'And this evidence from the document: "{evidence.text}"',
            "",
            "Does the evidence support the claim?",
            "Answer with one of: supported, partially_supported, unsupported.",
            "Provide a brief reasoning.",
        ]
    )
