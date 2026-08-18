"""Normalization helpers shared by every SearchProvider (RDA-015).

These are pure functions on purpose: they take whatever a provider (or the
NormalizedSearchResult DTO itself) hands them and return a value in the
DTO's normalized shape, without knowing anything about OpenAlex/Crossref or
any other upstream API.

Design decisions:

- Optional scalars (title, abstract, doi, url) normalize to ``None`` when
  absent or invalid, never to ``""``. An empty string is not "no value", it
  is a source of ambiguity (was it truly empty or just not sent?) that
  ``None`` avoids downstream (e.g. ``if result.doi:`` works either way).
- Optional lists (authors) normalize to ``[]``, never ``None``, so callers
  can always iterate without a None-check.
- ``publication_year`` is validated against a plausible range (1000-2100)
  because an out-of-range year is almost certainly bad data (typo, parsing
  bug) that would otherwise silently corrupt sorting/filtering later.
- ``title`` is only stripped/blanked, not otherwise validated: unlike a
  year or a DOI, there is no structural rule a title must satisfy, so
  rejecting it would discard real (if unusual) data for no benefit.
- DOI and URL are validated against a minimal structural shape. Invalid
  values become ``None`` on the field itself (so a broken provider payload
  never breaks the DTO), but the raw original value is preserved by the
  caller under ``metadata["raw_doi"]`` / ``metadata["raw_url"]`` so no
  information is silently discarded.
"""

import re
from typing import Any
from urllib.parse import urlparse

MIN_PUBLICATION_YEAR = 1000
MAX_PUBLICATION_YEAR = 2100

_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$")
_DOI_URL_PREFIXES = ("https://doi.org/", "http://doi.org/", "doi:")


def normalize_title(title: Any) -> str | None:
    """Trim whitespace; blank/non-string titles become None."""
    if not isinstance(title, str):
        return None
    stripped = title.strip()
    return stripped or None


def normalize_authors(authors: Any) -> list[str]:
    """Normalize an author list independent of the source shape.

    Accepts a list of strings, trims each, and drops blank/non-string
    entries. Non-list input (including None) normalizes to [].
    """
    if not isinstance(authors, list):
        return []
    cleaned: list[str] = []
    for author in authors:
        if isinstance(author, str):
            stripped = author.strip()
            if stripped:
                cleaned.append(stripped)
    return cleaned


def normalize_abstract(abstract: Any) -> str | None:
    """Trim whitespace; blank/non-string abstracts become None."""
    if not isinstance(abstract, str):
        return None
    stripped = abstract.strip()
    return stripped or None


def normalize_year(year: Any) -> int | None:
    """Normalize a publication year.

    Accepts an int or a numeric string; rejects bool (a bool is technically
    an int in Python but never a valid year) and anything outside
    [MIN_PUBLICATION_YEAR, MAX_PUBLICATION_YEAR].
    """
    if isinstance(year, bool):
        return None
    if isinstance(year, int):
        candidate = year
    elif isinstance(year, str) and year.strip().lstrip("-").isdigit():
        candidate = int(year.strip())
    else:
        return None

    if MIN_PUBLICATION_YEAR <= candidate <= MAX_PUBLICATION_YEAR:
        return candidate
    return None


def normalize_doi(doi: Any) -> str | None:
    """Normalize and validate a DOI.

    Strips a leading "https://doi.org/" (or "doi:") prefix if present, then
    checks the result against the general DOI shape (``10.<4-9 digits>/<suffix>``).
    Returns None when the input isn't a recognizable DOI.
    """
    if not isinstance(doi, str):
        return None
    candidate = doi.strip()
    lowered = candidate.lower()
    for prefix in _DOI_URL_PREFIXES:
        if lowered.startswith(prefix):
            candidate = candidate[len(prefix):]
            break

    if _DOI_PATTERN.match(candidate):
        return candidate
    return None


def normalize_url(url: Any) -> str | None:
    """Normalize and validate a URL.

    Only accepts http(s) URLs with a non-empty host; anything else
    (malformed strings, other schemes, non-string input) becomes None.
    """
    if not isinstance(url, str):
        return None
    candidate = url.strip()
    if not candidate:
        return None
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return candidate
    return None
