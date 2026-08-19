"""Domain exceptions for retrieval (RDA-024).

Kept provider-agnostic on purpose, following the same convention as
app.services.embeddings.exceptions and app.services.search.exceptions:
concrete providers translate their own transport-level failures into these
so callers of DocumentRetriever never need to know which API is behind it.
"""


class RetrievalError(Exception):
    """Base class for every error raised by the retrieval layer."""
