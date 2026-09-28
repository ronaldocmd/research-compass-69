"""Helpers shared by the multi-source search providers (RDA-066).

Keeps the per-provider adapters small: one HTTP wrapper that maps transport
failures onto the search exception hierarchy, query translators for sources
that do not speak the planner's boolean syntax, and a PDF-URL heuristic used
to prefer directly downloadable links when merging duplicates.
"""

import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.search.exceptions import (
    SearchProviderError,
    SearchProviderHTTPError,
    SearchProviderInvalidResponseError,
    SearchProviderRateLimitError,
    SearchProviderTimeoutError,
)


def get_response(
    name: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float,
    client: httpx.Client | None = None,
) -> httpx.Response:
    """GET ``url`` and map failures to SearchProvider exceptions."""
    try:
        if client is not None:
            response = client.get(
                url, params=params, headers=headers, timeout=timeout, follow_redirects=True
            )
        else:
            response = httpx.get(
                url, params=params, headers=headers, timeout=timeout, follow_redirects=True
            )
    except httpx.TimeoutException as exc:
        raise SearchProviderTimeoutError(f"{name} request timed out") from exc
    except httpx.HTTPError as exc:
        raise SearchProviderError(f"{name} request failed: {exc}") from exc

    if response.status_code == 429:
        raise SearchProviderRateLimitError(f"{name} rate limit exceeded (HTTP 429)")
    if response.status_code >= 400:
        raise SearchProviderHTTPError(
            response.status_code, f"{name} returned HTTP {response.status_code}"
        )
    return response


def parse_json_object(name: str, response: httpx.Response) -> dict[str, Any]:
    """Return the response body as a JSON object or raise InvalidResponse."""
    try:
        payload = response.json()
    except ValueError as exc:
        raise SearchProviderInvalidResponseError(f"{name} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise SearchProviderInvalidResponseError(
            f"{name} returned an unexpected payload shape"
        )
    return payload


_TOKEN = re.compile(r'"[^"]+"|\(|\)|\bAND\b|\bOR\b|\bNOT\b|[^\s()"]+')
_OPERATORS = {"AND", "OR", "NOT"}


def strip_boolean(query: str) -> str:
    """Reduce a boolean query to plain keywords (for keyword-only APIs).

    ``("rare earth" OR REE) AND Brazil`` -> ``rare earth REE Brazil``.
    """
    words: list[str] = []
    for token in _TOKEN.findall(query):
        if token in _OPERATORS or token in ("(", ")"):
            continue
        words.append(token.strip('"'))
    return " ".join(w for w in words if w).strip() or query.strip()


def to_arxiv_query(query: str) -> str:
    """Translate a boolean query to arXiv syntax (``all:`` field prefixes).

    ``"rare earth" AND Brazil`` -> ``all:"rare earth" AND all:Brazil``.
    Adjacent terms without an operator are joined with AND; NOT becomes
    ANDNOT, as arXiv expects.
    """
    out: list[str] = []
    previous_was_term = False
    for token in _TOKEN.findall(query):
        if token in ("AND", "OR"):
            out.append(token)
            previous_was_term = False
        elif token == "NOT":
            out.append("ANDNOT")
            previous_was_term = False
        elif token == "(":
            if previous_was_term:
                out.append("AND")
            out.append("(")
            previous_was_term = False
        elif token == ")":
            out.append(")")
            previous_was_term = True
        else:
            if previous_was_term:
                out.append("AND")
            out.append(f"all:{token}")
            previous_was_term = True
    return " ".join(out).strip() or f"all:{query.strip()}"


def is_pdf_url(url: str | None) -> bool:
    """Heuristic: does ``url`` point straight at a PDF (not a landing page)?"""
    if not url:
        return False
    parsed = urlparse(url)
    path = parsed.path.lower()
    if path.endswith(".pdf"):
        return True
    if "/pdf/" in path or path.endswith("/pdf"):
        return True
    return "pdf=render" in parsed.query.lower()


_TAGS = re.compile(r"<[^>]+>")


def strip_tags(text: str | None) -> str | None:
    """Remove inline markup (e.g. JATS tags in Europe PMC abstracts)."""
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", _TAGS.sub(" ", text)).strip()
    return cleaned or None
