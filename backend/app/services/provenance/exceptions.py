"""Domain exceptions for provenance (RDA-029)."""


class ProvenanceError(Exception):
    """Base class for every error raised by the provenance layer."""


class MissingProvenanceError(ProvenanceError):
    """A claim or evidence is missing the provenance it needs."""
