"""Retrieval service (RDA-024)."""

from app.services.retrieval.exceptions import RetrievalError
from app.services.retrieval.retriever import DocumentRetriever, cosine_similarity
from app.services.retrieval.schemas import IndexedChunk, RetrievedChunk, RetrievalResult

__all__ = [
    "DocumentRetriever",
    "IndexedChunk",
    "RetrievalError",
    "RetrievalResult",
    "RetrievedChunk",
    "cosine_similarity",
]
