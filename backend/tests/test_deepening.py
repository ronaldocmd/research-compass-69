"""Deepening rounds: a follow-up run builds on earlier results."""

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.chunk import ChunkRecord
from app.models.document import Document
from app.models.evidence_chain import ClaimRecord, ConfidenceRecord, ValidationRecord
from app.repositories.research_repository import ResearchRepository
from app.schemas.search import NormalizedSearchResult
from app.services.claims.schemas import Claim
from app.services.confidence.schemas import ConfidenceLevel
from app.services.orchestration.nodes import ResearchNodes, SynthesisResponse
from app.services.orchestration.wiring import WorkflowServices
from app.services.planning.planner import build_planning_prompt
from app.services.planning.schemas import ResearchPlanInput
from app.services.validation.schemas import ValidationStatus
from app.services.workflow.state import WorkflowStage
from app.services.workflow.state_manager import WorkflowStateManager

NOW = datetime.now(UTC)


def _input(**kw) -> ResearchPlanInput:
    return ResearchPlanInput(research_id=uuid.uuid4(), objective="o", question="q", **kw)


def test_first_run_prompt_has_no_followup_section() -> None:
    prompt = build_planning_prompt(_input(), min_tasks=1, max_tasks=5)
    assert "FOLLOW-UP" not in prompt


def test_followup_prompt_lists_previous_queries_titles_and_focus() -> None:
    prompt = build_planning_prompt(
        _input(
            previous_queries=['"rare earth" AND Brazil'],
            known_titles=["Paper Alpha"],
            focus="impacto ambiental",
        ),
        min_tasks=1, max_tasks=5,
    )
    assert "FOLLOW-UP" in prompt
    assert '"rare earth" AND Brazil' in prompt
    assert "Paper Alpha" in prompt
    assert "impacto ambiental" in prompt


def test_retrieval_query_includes_focus() -> None:
    nodes = ResearchNodes()
    state = WorkflowStateManager.create_initial_state(uuid.uuid4()).model_copy(
        update={"research_question": "Qual o cenário?", "research_focus": "ambiental"}
    )
    task = SimpleNamespace(title="t", description="")
    assert nodes._retrieval_query(state, task) == "Qual o cenário? ambiental"


@pytest.fixture
def seeded():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, future=True)() as db:
        research = ResearchRepository(db).create(title="t", objective="o", question="q")
        rid = research.id
        doc = Document(
            id=uuid.uuid4(), research_id=rid, source="openalex", title="Known Paper",
            doi="10.1/known", authors=[], document_metadata={},
        )
        db.add(doc)
        db.flush()
        claimed, unclaimed = uuid.uuid4(), uuid.uuid4()
        for cid, text in ((claimed, "used chunk"), (unclaimed, "untouched chunk")):
            db.add(ChunkRecord(
                chunk_id=cid, document_id=doc.id, chunk_index=0, text=text, page_number=1,
                char_count=len(text), embedding=[1.0, 0.0], embedding_model="m",
                embedding_dimension=2, embedded_at=NOW,
            ))
        claim_id = uuid.uuid4()
        db.add(ClaimRecord(
            claim_id=claim_id, research_id=rid, text="Old supported claim",
            document_id=doc.id, page_number=1, chunk_ids=[str(claimed)], extracted_at=NOW,
        ))
        db.flush()
        db.add(ValidationRecord(
            validation_id=uuid.uuid4(), research_id=rid, claim_id=claim_id,
            evidence_id=uuid.uuid4(), status=ValidationStatus.SUPPORTED, reasoning="r",
            validated_at=NOW, model_used="m",
        ))
        db.add(ConfidenceRecord(
            confidence_id=uuid.uuid4(), research_id=rid, claim_id=claim_id,
            level=ConfidenceLevel.HIGH, score=0.9, reasoning="r", factors={}, scored_at=NOW,
        ))
        db.commit()

        class _Search:
            def search(self, query):
                return [
                    NormalizedSearchResult(source="openalex", title="Known Paper", doi="10.1/known"),
                    NormalizedSearchResult(source="openalex", title="Brand New Paper", doi="10.9/new"),
                ]

        fake = object()
        services = WorkflowServices(
            db, rid, search_service=_Search(), downloader=fake, storage=fake,
            extractor=fake, chunker=fake, embedding_service=SimpleNamespace(provider=fake),
            planner=fake, claim_extractor=fake, evidence_extractor=fake, llm=fake,
            retriever=fake, validator=fake, provenance_resolver=fake, confidence_scorer=fake,
        )
        yield services, rid, claim_id, unclaimed


def test_index_is_seeded_with_only_unclaimed_prior_chunks(seeded) -> None:
    services, _, _, unclaimed = seeded
    assert [c.chunk_id for c in services._index] == [unclaimed]


def test_search_drops_documents_collected_in_earlier_rounds(seeded) -> None:
    services, *_ = seeded
    results = services.search("anything")
    assert [r.title for r in results] == ["Brand New Paper"]


def test_history_reports_titles_already_collected(seeded) -> None:
    services, rid, *_ = seeded
    queries, titles = services.load_history(rid)
    assert queries == []
    assert "Known Paper" in titles


def test_prior_claims_loader_returns_supported_claims_and_honours_exclusion(seeded) -> None:
    services, rid, claim_id, _ = seeded
    loaded = services.load_prior_claims(rid, [])
    assert [(c.text, lvl) for c, lvl in loaded] == [("Old supported claim", ConfidenceLevel.HIGH)]
    assert services.load_prior_claims(rid, [claim_id]) == []


def test_synthesis_covers_prior_claims_when_this_round_found_none() -> None:
    prompts: list[str] = []

    class _LLM:
        def complete(self, prompt, model):
            prompts.append(prompt)
            return SynthesisResponse(summary="combined")

    saved: list[str] = []
    prior = Claim(
        claim_id=uuid.uuid4(), text="Old supported claim", chunk_ids=[uuid.uuid4()],
        document_id=uuid.uuid4(), page_number=1, extracted_at=NOW,
    )
    nodes = ResearchNodes(
        llm=_LLM(), summary_saver=lambda rid, s: saved.append(s),
        prior_claims_loader=lambda rid, exclude: [
            (prior, ConfidenceLevel.HIGH),
            (prior.model_copy(update={"text": "weak one"}), ConfidenceLevel.LOW),
        ],
    )
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())

    state = asyncio.run(nodes.synthesis_node(state))

    assert state.current_stage == WorkflowStage.COMPLETED
    assert "Old supported claim" in prompts[0]
    assert "weak one" not in prompts[0]  # below SYNTHESIS_MIN_CONFIDENCE
    assert saved == ["combined"]
    assert state.synthesis_stats["included_from_previous_rounds"] == 1
