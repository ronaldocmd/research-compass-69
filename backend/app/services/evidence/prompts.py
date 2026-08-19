"""Prompt templates for evidence extraction (RDA-026)."""

from app.services.claims.schemas import Claim
from app.services.retrieval.schemas import RetrievedChunk


def build_evidence_extraction_prompt(claim: Claim, chunks: list[RetrievedChunk]) -> str:
    """Build the prompt that asks the LLM to locate evidence for a claim.

    Each source chunk is presented with its ``chunk_id`` (the reference the
    LLM must echo back), page number, optional section/title, and text.
    """
    lines = [
        "You are a research assistant verifying whether a claim is supported",
        "by the provided source chunks.",
        "",
        "Claim:",
        claim.text,
        "",
        "For the claim above, examine the source chunks and produce evidence.",
        "Rules:",
        "- 'text' must be the exact, verbatim passage from a chunk that",
        "  supports or informs the claim. Never invent or rewrite text.",
        "- 'chunk_id' is the id of the chunk the passage comes from.",
        "- 'status' is:",
        "    'supported' when a passage directly supports the claim;",
        "    'inconclusive' when chunks relate only partially/ambiguously;",
        "    'unsupported' when no chunk supports the claim.",
        "- For 'unsupported', set 'text' and 'chunk_id' to null.",
        "",
        "Source chunks:",
    ]
    for chunk in chunks:
        lines.append(_format_chunk(chunk))
    return "\n".join(lines)


def _format_chunk(chunk: RetrievedChunk) -> str:
    header = f"[chunk_id: {chunk.chunk_id}] (page {chunk.page_number})"
    if chunk.section:
        header += f", section={chunk.section!r}"
    if chunk.document_title:
        header += f", title={chunk.document_title!r}"
    return f"{header}\n{chunk.text}"
