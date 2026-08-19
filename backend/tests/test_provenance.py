"""Tests for ProvenanceResolver (RDA-029)."""

import uuid
from datetime import UTC, datetime

import pytest

from app.services.claims.schemas import Claim
from app.services.evidence.schemas import Evidence, EvidenceStatus
from app.services.provenance.exceptions import MissingProvenanceError
from app.services.provenance.resolver import (
    ProvenanceResolver,
    assert_claim_has_provenance,
    assert_evidence_has_provenance,
)
from app.services.provenance.schemas import DocumentSource
from app.services.retrieval.schemas import RetrievedChunk


def _claim(*, text="X reduces latency", chunk_ids=None, claim_id=None) -> Claim:
    return Claim(
        claim_id=claim_id or uuid.uuid4(),
        text=text,
        chunk_ids=chunk_ids if chunk_ids is not None else [],
        document_id=uuid.uuid4(),
        page_number=None,
        extracted_at=datetime.now(UTC),
    )


def _evidence(*, text="evidence text", chunk_id=None, evidence_id=None) -> Evidence:
    return Evidence(
        evidence_id=evidence_id or uuid.uuid4(),
        claim_id=uuid.uuid4(),
        text=text,
        chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        page_number=None,
        status=EvidenceStatus.SUPPORTED,
        extracted_at=datetime.now(UTC),
    )


def _chunk(*, chunk_id=None, page_number=8, text="chunk text") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id or uuid.uuid4(),
        document_id=uuid.uuid4(),
        text=text,
        page_number=page_number,
        section=None,
        score=0.9,
        document_title=None,
    )


def _source(
    *,
    document_id=None,
    title="Deep Learning Survey",
    url="https://example.org/x",
    doi="10.1234/x",
    page_number=8,
    chunk_id=None,
) -> DocumentSource:
    return DocumentSource(
        document_id=document_id or uuid.uuid4(),
        title=title,
        url=url,
        doi=doi,
        page_number=page_number,
        chunk_id=chunk_id or uuid.uuid4(),
    )


def _resolve(*, chunk_id=None, page_number=8, doi="10.1234/x", evidence_chunk_id=True):
    chunk_id = chunk_id or uuid.uuid4()
    claim = _claim(chunk_ids=[chunk_id])
    evidence = _evidence(chunk_id=chunk_id if evidence_chunk_id else None)
    chunk = _chunk(chunk_id=chunk_id, page_number=page_number)
    source = _source(doi=doi, chunk_id=chunk_id, page_number=page_number)
    return ProvenanceResolver().resolve(claim, evidence, chunk, source)


def test_full_chain_resolves_completely() -> None:
    chunk_id = uuid.uuid4()
    claim = _claim(chunk_ids=[chunk_id])
    evidence = _evidence(chunk_id=chunk_id)
    chunk = _chunk(chunk_id=chunk_id, page_number=8)
    source = _source(chunk_id=chunk_id, page_number=8)

    chain = ProvenanceResolver().resolve(claim, evidence, chunk, source)

    assert chain.claim_id == claim.claim_id
    assert chain.is_complete is True
    assert chain.resolved_at is not None
    assert [link.level for link in chain.chain] == [
        "claim",
        "evidence",
        "chunk",
        "page",
        "document",
        "source",
    ]


def test_missing_doi_makes_chain_incomplete() -> None:
    chain = _resolve(doi=None)

    assert chain.is_complete is False
    assert "source" not in {link.level for link in chain.chain}


def test_missing_evidence_chunk_id_makes_chain_incomplete() -> None:
    chain = _resolve(evidence_chunk_id=False)

    assert chain.is_complete is False
    assert "chunk" not in {link.level for link in chain.chain}
    assert "page" not in {link.level for link in chain.chain}


def test_assert_claim_has_provenance_raises() -> None:
    with pytest.raises(MissingProvenanceError):
        assert_claim_has_provenance(_claim(chunk_ids=[]))


def test_assert_evidence_has_provenance_raises() -> None:
    with pytest.raises(MissingProvenanceError):
        assert_evidence_has_provenance(_evidence(chunk_id=None))


def test_guards_do_not_raise_on_valid_input() -> None:
    assert_claim_has_provenance(_claim(chunk_ids=[uuid.uuid4()]))
    assert_evidence_has_provenance(_evidence(chunk_id=uuid.uuid4()))


def test_chain_order_claim_first_source_last() -> None:
    chain = _resolve()

    assert chain.chain[0].level == "claim"
    assert chain.chain[-1].level == "source"


def test_each_link_has_non_empty_fields() -> None:
    chain = _resolve()

    for link in chain.chain:
        assert link.level
        assert link.id
        assert link.description


def test_chunk_link_contains_page_number() -> None:
    chunk_id = uuid.uuid4()
    claim = _claim(chunk_ids=[chunk_id])
    evidence = _evidence(chunk_id=chunk_id)
    chunk = _chunk(chunk_id=chunk_id, page_number=8)
    source = _source(chunk_id=chunk_id)

    chain = ProvenanceResolver().resolve(claim, evidence, chunk, source)

    chunk_link = next(link for link in chain.chain if link.level == "chunk")
    assert "Page 8" in chunk_link.description


def test_resolve_does_not_raise_on_missing_provenance() -> None:
    claim = _claim(chunk_ids=[])
    evidence = _evidence(chunk_id=None)
    chunk = _chunk()
    source = _source(doi=None)

    chain = ProvenanceResolver().resolve(claim, evidence, chunk, source)

    assert chain.is_complete is False
    assert [link.level for link in chain.chain] == ["claim", "evidence", "document"]
