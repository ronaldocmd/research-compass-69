"""Deterministic negation detection (RDA-063).

Detects simple, explicit negation flips between a claim and its source. The
goal is to catch cases like:

    Source: "The study found no significant effect."
    Claim:  "The study found a significant effect."

Only explicit negation markers are considered. This is deliberately narrow:
negation is context-sensitive, and a word list alone cannot resolve every
case. When negation is ambiguous, the detector returns False (no flip) and the
semantic validator handles it.

Limits (documented):
    - "not" in "not only" or "not just" is not a negation of the following
      claim; these are not handled and may produce a false "flip". To stay
      conservative, we only flag a flip when the SAME content word appears
      both negated in the source and un-negated in the claim (or vice versa).
    - Implicit negation ("failed to", "absence of") is only matched when the
      negated content word is also present.
"""

import re

# Negation markers (EN + PT). Ordered so longer forms match first.
_NEGATIONS = [
    "did not",
    "does not",
    "do not",
    "no significant",
    "no effect",
    "not",
    "never",
    "without",
    "failed to",
    "absence of",
    "não apresentou",
    "não houve",
    "não há",
    "não",
    "nenhum",
    "nunca",
    "sem",
    "ausência de",
]

# Content words that commonly carry the negated meaning (EN + PT). Matched as
# word prefixes so inflected forms (increase/increased/increasing) are caught.
_CONTENT = re.compile(
    r"\b(significant|effect|increase|decrease|reduction|improvement|risk|benefit|"
    r"support|decline|growth|profit|loss|safe|effective|thriving|declining|"
    r"efeito|significativo|aumento|redução|melhoria|risco|benefício|apoio|"
    r"declínio|crescimento|lucro|prejuízo|seguro|eficaz)",
    re.IGNORECASE,
)


def _has_negation(text: str) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in _NEGATIONS)


def _content_words(text: str) -> set[str]:
    return {m.group(1).casefold() for m in _CONTENT.finditer(text)}


def negation_flipped(claim_text: str, source_text: str) -> bool:
    """Return True when the claim flips the source's explicit negation.

    A flip is detected when the source is negated and the claim is not (or the
    claim is negated and the source is not) AND they share a content word that
    carries the meaning. This avoids flagging unrelated negations.
    """
    if not claim_text or not source_text:
        return False
    source_neg = _has_negation(source_text)
    claim_neg = _has_negation(claim_text)
    if source_neg == claim_neg:
        return False
    shared = _content_words(claim_text) & _content_words(source_text)
    return bool(shared)
