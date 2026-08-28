"""Safe text normalization for grounding (RDA-063).

Only normalizations that preserve meaning are applied. The goal is to make
verbatim passages comparable across whitespace, case, Unicode and punctuation
differences WITHOUT removing semantically relevant information (numbers,
negation words, units).

Safe normalizations:
    - Unicode NFKC (composes/decomposes compatible forms: ligatures, full-width
      digits, curly quotes -> straight).
    - Collapse all whitespace (spaces, tabs, newlines) to a single space.
    - Case folding (lowercase) for comparison.
    - Strip surrounding punctuation/whitespace.

NOT applied (would remove meaning):
    - Removing digits or number tokens.
    - Removing negation words (no, not, never, não, sem, ...).
    - Removing units or currency symbols.
    - Stemming/lemmatization (too aggressive for grounding).
"""

import re
import unicodedata

# Collapse any run of whitespace (including newlines/tabs) to a single space.
_WS = re.compile(r"\s+")
# Strip leading/trailing punctuation and whitespace.
_EDGE = re.compile(r"^[\s\W]+|[\s\W]+$")


def normalize(text: str) -> str:
    """Return a comparison-safe normalized form of ``text``.

    Preserves all alphanumeric content (including digits and negation words)
    while removing only formatting differences.
    """
    if not text:
        return ""
    # NFKC: full-width digits, ligatures, curly quotes -> canonical forms.
    text = unicodedata.normalize("NFKC", text)
    # Collapse whitespace.
    text = _WS.sub(" ", text)
    # Case fold for comparison.
    text = text.casefold()
    # Strip edge punctuation/whitespace.
    text = _EDGE.sub("", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    """Return the alphanumeric tokens of ``text`` (for overlap checks)."""
    return re.findall(r"\w+", normalize(text))
