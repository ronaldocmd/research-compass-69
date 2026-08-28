"""Prompt templates for evidence validation (RDA-028)."""

from app.services.claims.schemas import Claim
from app.services.evidence.schemas import Evidence


def build_validation_prompt(claim: Claim, evidence: Evidence) -> str:
    """Build an independent validation prompt for a claim/evidence pair.

    Deliberately excludes the RDA-026 status so the validator is not biased
    by the earlier extraction's classification: the model only sees the claim
    text and the evidence text.

    RDA-064: the prompt was expanded with operational definitions of each
    status and explicit guidance on the semantic failure modes the baseline
    benchmark exposed (correlation vs causation, over-generalization, scope,
    temporal, conditional, and fabrication). The baseline validator over-used
    ``partially_supported`` for claims the evidence does not actually support
    and never reliably emitted ``contradicted``.
    """
    return "\n".join(
        [
            "You are validating whether a piece of evidence supports a claim.",
            "",
            f'Given this claim: "{claim.text}"',
            f'And this evidence from the document: "{evidence.text}"',
            "",
            "Decide how the evidence relates to the claim. Answer with exactly "
            "one of: supported, partially_supported, unsupported, contradicted.",
            "",
            "Definitions:",
            "- supported: the evidence directly and fully establishes the claim "
            "as stated, including its scope, quantifiers, numbers, and time.",
            "- partially_supported: the evidence supports part of the claim but "
            "not all of it (e.g. it supports one of several assertions, or a "
            "narrower version of the claim).",
            "- unsupported: the evidence is relevant but does not establish the "
            "claim as stated. This includes: correlation/association presented "
            "as causation; a claim generalized beyond the evidence's scope "
            "(population, geography, time, or quantifiers such as 'all' vs "
            "'some'); a conditional or hypothetical statement asserted as "
            "certain; and plausible-sounding statements the evidence does not "
            "actually contain.",
            "- contradicted: the evidence directly contradicts the claim (e.g. "
            "opposite numbers, opposite direction, or a statement that negates "
            "the claim).",
            "",
            "Guidance:",
            "- Association is not causation. If the evidence says 'associated' "
            "or 'linked' and the claim says 'causes', the claim is unsupported, "
            "not partially supported.",
            "- Do not generalize. If the evidence covers a subset (a population, "
            "a region, a year) and the claim extends to all or to a broader "
            "scope, the claim is unsupported unless the evidence explicitly "
            "supports the broader scope.",
            "- A conditional or hypothetical ('may', 'could', 'if') does not "
            "support a categorical claim.",
            "- If the evidence states the opposite of the claim, answer "
            "contradicted.",
            "",
            "Provide a brief reasoning.",
        ]
    )
