"""ProvenanceResolver (RDA-029).

Assembles the full origin chain of a claim from already-resolved objects
(Claim, Evidence, RetrievedChunk, DocumentSource). It does not touch the
database: it only wires the pieces together and reports whether the chain is
complete.

Chain order (most derived -> most original):

    claim -> evidence -> chunk -> page -> document -> source

Only the links whose data is present are recorded; ``is_complete`` is True
only when all six levels are present. Missing links never raise here — use the
``assert_*_has_provenance`` guards when provenance is required.
"""

from datetime import UTC, datetime

from app.services.claims.schemas import Claim
from app.services.evidence.schemas import Evidence
from app.services.provenance.exceptions import MissingProvenanceError
from app.services.provenance.schemas import DocumentSource, ProvenanceChain, ProvenanceLink
from app.services.retrieval.schemas import RetrievedChunk

EXPECTED_LEVELS = ("claim", "evidence", "chunk", "page", "document", "source")


def assert_claim_has_provenance(claim: Claim) -> None:
    """Raise MissingProvenanceError when the claim has no chunk provenance."""
    if not claim.chunk_ids:
        raise MissingProvenanceError(
            f"Claim {claim.claim_id} has no chunk_ids provenance"
        )


def assert_evidence_has_provenance(evidence: Evidence) -> None:
    """Raise MissingProvenanceError when the evidence has no chunk provenance."""
    if evidence.chunk_id is None:
        raise MissingProvenanceError(
            f"Evidence {evidence.evidence_id} has no chunk_id provenance"
        )


class ProvenanceResolver:
    """Builds a ProvenanceChain from already-resolved objects."""

    def resolve(
        self,
        claim: Claim,
        evidence: Evidence,
        chunk: RetrievedChunk,
        document_source: DocumentSource,
    ) -> ProvenanceChain:
        chain: list[ProvenanceLink] = []

        # claim and evidence links are always recorded (the objects exist).
        chain.append(
            ProvenanceLink(
                level="claim",
                id=str(claim.claim_id),
                description=claim.text or "Claim",
            )
        )
        chain.append(
            ProvenanceLink(
                level="evidence",
                id=str(evidence.evidence_id),
                description=evidence.text or "Evidence",
            )
        )

        # chunk + page exist only when the evidence is grounded to a chunk.
        if evidence.chunk_id is not None:
            chain.append(
                ProvenanceLink(
                    level="chunk",
                    id=str(chunk.chunk_id),
                    description=_chunk_description(chunk),
                )
            )
            chain.append(
                ProvenanceLink(
                    level="page",
                    id=f"page-{chunk.page_number}",
                    description=_page_description(chunk, document_source),
                )
            )

        # document always exists (document_id is required on DocumentSource).
        if document_source.document_id is not None:
            chain.append(
                ProvenanceLink(
                    level="document",
                    id=str(document_source.document_id),
                    description=document_source.title or "Document",
                )
            )

        # source exists only when the original source is identifiable by DOI.
        if document_source.doi is not None:
            chain.append(
                ProvenanceLink(
                    level="source",
                    id=document_source.doi,
                    description=_source_description(document_source),
                )
            )

        present = {link.level for link in chain}
        is_complete = present == set(EXPECTED_LEVELS)

        return ProvenanceChain(
            claim_id=claim.claim_id,
            chain=chain,
            resolved_at=datetime.now(UTC),
            is_complete=is_complete,
        )


def _chunk_description(chunk: RetrievedChunk) -> str:
    text = chunk.text or "Chunk"
    return f"Page {chunk.page_number}: {text}"


def _page_description(chunk: RetrievedChunk, source: DocumentSource) -> str:
    title = source.title or "the document"
    return f"Page {chunk.page_number} of '{title}'"


def _source_description(source: DocumentSource) -> str:
    description = f"DOI: {source.doi}"
    if source.url:
        description += f" — URL: {source.url}"
    return description
