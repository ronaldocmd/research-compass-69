"""Prompt templates for claim extraction (RDA-025)."""

from app.services.retrieval.schemas import RetrievedChunk


def build_claim_extraction_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    """Build the prompt that asks the LLM to extract claims from chunks.

    Each source chunk is presented with its ``chunk_id`` (the reference the
    LLM must echo back per claim), page number, optional section and title,
    and its text.
    """
    lines = [
        "You are a research assistant extracting verifiable factual claims.",
        "Given the user's question and a set of source chunks, list every",
        "factual, verifiable claim that is directly supported by the chunks.",
        "",
        "Rules:",
        "- Return only claims that are explicitly supported by the chunks.",
        "- For every claim, include the chunk_ids that support it.",
        "- Do not invent claims; if a chunk supports no claim, skip it.",
        "- Respond with a JSON object matching the requested schema: a",
        "  'claims' list where each item has 'text' and 'chunk_ids'.",
        "",
        f"User question: {query}",
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
