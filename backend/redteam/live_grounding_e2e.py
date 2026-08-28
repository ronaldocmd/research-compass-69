"""RDA-063 live end-to-end test: grounding gate + real LLM validator.

Runs the validation_node with the real EvidenceValidator (LLM) and the
deterministic grounding layer against adversarial claim/evidence/chunk cases.
Verifies that a deterministic grounding failure overrides the LLM result.

This is a live test (makes real LLM calls) and is not part of the unit suite.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from app.services.claims.schemas import Claim
from app.services.evidence.schemas import Evidence, EvidenceStatus
from app.services.orchestration.nodes import ResearchNodes
from app.services.provenance.schemas import DocumentSource
from app.services.retrieval.schemas import RetrievedChunk
from app.services.validation.schemas import ValidationStatus
from app.services.workflow.state import ResearchWorkflowState
from app.services.workflow.state_manager import WorkflowStateManager


def _claim(text: str) -> Claim:
    return Claim(
        claim_id=uuid.uuid4(), text=text, chunk_ids=[uuid.uuid4()],
        document_id=uuid.uuid4(), page_number=1, extracted_at=datetime.now(UTC),
    )


def _evidence(claim: Claim, text: str) -> Evidence:
    return Evidence(
        evidence_id=uuid.uuid4(), claim_id=claim.claim_id, text=text,
        chunk_id=claim.chunk_ids[0], document_id=claim.document_id,
        page_number=1, status=EvidenceStatus.SUPPORTED,
        extracted_at=datetime.now(UTC),
    )


def _chunk(claim: Claim, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=claim.chunk_ids[0], document_id=claim.document_id, text=text,
        page_number=1, section=None, score=0.9, document_title="Source",
    )


def _state(claim, evidence, chunk) -> ResearchWorkflowState:
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())
    return state.model_copy(
        update={"claims": [claim], "evidence_items": [evidence], "retrieved_chunks": [chunk]}
    )


def _nodes() -> ResearchNodes:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.services.orchestration.wiring import WorkflowServices

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    factory = sessionmaker(bind=engine, future=True)
    db = factory()
    services = WorkflowServices(db, uuid.uuid4())
    return ResearchNodes(
        validator=services.validator,
        provenance_resolver=services.provenance_resolver,
        confidence_scorer=services.confidence_scorer,
        document_resolver=lambda doc_id, chunk: DocumentSource(
            document_id=doc_id, title="Doc", url="https://x", doi="10.1/x",
            page_number=chunk.page_number, chunk_id=chunk.chunk_id,
        ),
    )


CASES = [
    # (label, claim, evidence, chunk, expected_final_status)
    (
        "supported",
        "Production increased by 12% in 2022.",
        "Production increased by 12% in 2022.",
        "Production increased by 12% in 2022.",
        ValidationStatus.SUPPORTED,
    ),
    (
        "number_change",
        "Production increased by 21%.",
        "Production increased by 21%.",
        "Production increased by 12%.",
        ValidationStatus.PARTIALLY_SUPPORTED,
    ),
    (
        "negation",
        "The study found a significant effect of the drug.",
        "The study found a significant effect of the drug.",
        "The study found no significant effect of the drug.",
        ValidationStatus.CONTRADICTED,
    ),
    (
        "fabricated",
        "Vitamin D reduces severe respiratory infection.",
        "A randomized trial of 5,000 participants found that daily vitamin D supplementation reduced the incidence of severe respiratory infection by 40%.",
        "Vitamin D is important for bone health and immune function.",
        ValidationStatus.UNSUPPORTED,
    ),
]


async def main() -> None:
    nodes = _nodes()
    for label, claim_text, evidence_text, chunk_text, expected in CASES:
        claim = _claim(claim_text)
        evidence = _evidence(claim, evidence_text)
        chunk = _chunk(claim, chunk_text)
        state = _state(claim, evidence, chunk)
        try:
            result = await nodes.validation_node(state)
            statuses = [v.status for v in result.validation_results]
            grounding = [g.status.value for g in result.grounding_results]
            actual = statuses[0] if statuses else None
            ok = actual == expected
            print(
                f"[{label:14s}] expected={expected.value:20s} "
                f"actual={actual.value if actual else 'NONE':20s} "
                f"grounding={grounding} {'PASS' if ok else 'FAIL'}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[{label:14s}] ERROR: {type(exc).__name__}: {str(exc)[:120]}")


if __name__ == "__main__":
    asyncio.run(main())
