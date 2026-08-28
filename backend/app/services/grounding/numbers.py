"""Deterministic numeric-entity detection (RDA-063).

Detects simple factual number changes that the LLM can miss. The goal is NOT
to interpret complex math — it is to catch objective alterations such as
12% vs 21%, 2024 vs 2023, 5 vs 5.0.

Approach:
    - Extract numeric tokens (integers, decimals, percentages, years, currency
      amounts) from a text.
    - Canonicalize each token to a comparable form (strip trailing zeros in
      decimals, normalize separators).
    - Compare the claim's numbers against the source's numbers. A number in
      the claim that has no equivalent in the source is a mismatch.

Limits (documented, not over-engineered):
    - Equivalent forms (1.2 billion vs 1,200 million) are NOT resolved: they
      are different tokens and would be flagged. This is conservative and
      acceptable — the semantic validator can reconcile them.
    - Ranges and negative values are tokenized as-is.
    - Currency symbols are preserved as context, not parsed.
"""

import re

# Matches a number token: optional sign, digits, optional decimal part,
# optional % or currency suffix. Also matches bare years.
_NUMBER = re.compile(
    r"(?<!\w)([+-]?\d+(?:[.,]\d+)?)\s*(%|percent|%|milh|million|billion|bi|mi|k|€|R\$|\$)?",
    re.IGNORECASE,
)


def extract_numbers(text: str) -> list[str]:
    """Return the canonical numeric tokens found in ``text``."""
    if not text:
        return []
    tokens: list[str] = []
    for match in _NUMBER.finditer(text):
        value = match.group(1)
        suffix = (match.group(2) or "").lower()
        tokens.append(_canonical(value, suffix))
    return tokens


def _canonical(value: str, suffix: str) -> str:
    """Canonicalize a numeric token for comparison.

    - Normalize decimal comma to dot (12,5 -> 12.5).
    - Strip trailing zeros in the decimal part (12.0 -> 12, 5.0 -> 5).
    - Keep the suffix (%, million, etc.) so 12% != 12.
    """
    value = value.replace(",", ".")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return f"{value}{suffix}"


def number_mismatches(claim_text: str, source_text: str) -> list[str]:
    """Return the claim's numeric tokens that have no equivalent in source.

    A claim number is considered consistent if the same canonical token
    appears in the source. Returns the list of mismatched claim tokens.
    """
    if not claim_text:
        return []
    claim_numbers = extract_numbers(claim_text)
    source_numbers = set(extract_numbers(source_text))
    return [n for n in claim_numbers if n not in source_numbers]
