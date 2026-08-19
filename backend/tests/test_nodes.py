"""Individual node tests (RDA-034).

Every service is replaced with a fake: no real LLM/search/DB calls.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from app.schemas.search import NormalizedSearchResult
from app.services.claims.schemas import Claim, ClaimExtractionResult
from app.services.evidence.schemas import Evidence, EvidenceExtractionResult, EvidenceStatus
from app.services.orchestration.nodes import ResearchNodes, SynthesisResponse
from app.services.planning.schemas import PlanTask, ResearchPlan, TaskStatus, TaskType
from app.services.retrieval.schemas import RetrievedChunk, RetrievalResult
from app.services.workflow.state import ResearchWorkflowState, WorkflowStage
from app.services.workflow.state_manager import WorkflowStateManager


def _run(node, state) -> ResearchWorkflowState:
    return asyncio.run(node(state))


def _initial(**updates) -> ResearchWorkflowState:
    state = WorkflowStateManager.create_initial_state(uuid.uuid4())
    return state.model_copy(update=updates)


def _task(title, task_type=TaskType.SEARCH) -> PlanTask:
    return PlanTask(
        task_id=uuid.uuid4(), title=title, description=f"{title} desc",
        priority=1, task_type=task_type, status=TaskStatus.PENDING,
    )


def _claim() -> Claim:
    return Claim(
        claim_id=uuid.uuid4(), text="a claim", chunk_ids=[uuid.uuid4()],
        document_id=uuid.uuid4(), page_number=1, extracted_at=datetime.now(UTC),
    )


def _evidence(claim_id) -> Evidence:
    return Evidence(
        evidence_id=uuid.uuid4(), claim_id=claim_id, text="evidence",
        chunk_id=uuid.uuid4(), document_id=uuid.uuid4(), page_number=1,
        status=EvidenceStatus.SUPPORTED, extracted_at=datetime.now(UTC),
    )


# --- planner_node ------------------------------------------------------------


class _FakePlanner:
    def __init__(self, plan: ResearchPlan) -> None:
        self._plan = plan
        self.received: list = []

    async def plan(self, plan_input):
        self.received.append(plan_input)
        return self._plan


def test_planner_node_generates_tasks() -> None:
    research_id = uuid.uuid4()
    plan = ResearchPlan(
        plan_id=uuid.uuid4(), research_id=research_id,
        tasks=[_task("t1"), _task("t2")], created_at=datetime.now(UTC),
    )
    planner = _FakePlanner(plan)
    nodes = ResearchNodes(planner=planner, research_loader=lambda rid: SimpleNamespace(objective="o", question="q"))

    state = _run(nodes.planner_node, _initial())

    assert [t.title for t in state.tasks] == ["t1", "t2"]
    assert state.plan_id == plan.plan_id
    assert state.budget.llm_calls == 1
    assert state.current_stage == WorkflowStage.SEARCHING
    assert planner.received[0].objective == "o"


def test_planner_node_missing_research_records_error() -> None:
    planner = _FakePlanner(ResearchPlan(plan_id=uuid.uuid4(), research_id=uuid.uuid4(), tasks=[], created_at=datetime.now(UTC)))
    nodes = ResearchNodes(planner=planner, research_loader=lambda rid: None)

    state = _run(nodes.planner_node, _initial())

    assert state.tasks == []
    assert state.errors and state.errors[-1].severity.value == "PERMANENT"


# --- search_node -------------------------------------------------------------


class _FakeSearch:
    def __init__(self, results) -> None:
        self._results = results
        self.calls: list[str] = []

    def search(self, query):
        self.calls.append(query)
        return self._results.get(query, [])


def test_search_node_accumulates_results() -> None:
    search = _FakeSearch({
        "Search A": [NormalizedSearchResult(source="openalex", title="A")],
        "Search B": [NormalizedSearchResult(source="openalex", title="B")],
    })
    nodes = ResearchNodes(search=search)
    state = _initial(tasks=[_task("Search A"), _task("Search B")])

    state = _run(nodes.search_node, state)

    assert [r.title for r in state.search_results] == ["A", "B"]
    assert state.budget.search_calls == 2
    assert state.current_stage == WorkflowStage.SELECTING


# --- selection_node ----------------------------------------------------------


def test_selection_node_filters_and_dedupes() -> None:
    nodes = ResearchNodes(max_documents=2)
    results = [
        NormalizedSearchResult(source="openalex", title="One", doi="10.1/a"),
        NormalizedSearchResult(source="openalex", title="One duplicate", doi="10.1/a"),
        NormalizedSearchResult(source="crossref", title="Two", doi="10.2/b"),
        NormalizedSearchResult(source="openalex", title="Three", doi="10.3/c"),
    ]
    state = _initial(search_results=results)

    state = _run(nodes.selection_node, state)

    assert len(state.selected_documents) == 2
    assert state.current_stage == WorkflowStage.PROCESSING


def test_selection_node_dedupes_by_title_when_no_doi() -> None:
    nodes = ResearchNodes(max_documents=10)
    results = [
        NormalizedSearchResult(source="openalex", title="Same Title"),
        NormalizedSearchResult(source="crossref", title="same title"),
        NormalizedSearchResult(source="openalex", title="Other"),
    ]
    state = _initial(search_results=results)

    state = _run(nodes.selection_node, state)

    assert len(state.selected_documents) == 2


# --- processing_node ---------------------------------------------------------


class _FakeProcessor:
    def __init__(self, *, chunks_by_id=None, fail_ids=None) -> None:
        self._chunks = chunks_by_id or {}
        self._fail = fail_ids or set()

    def __call__(self, doc_id):
        if doc_id in self._fail:
            raise RuntimeError("boom")
        return self._chunks.get(doc_id, [])


def test_processing_node_records_processed_and_failed() -> None:
    ok_doc = uuid.uuid4()
    bad_doc = uuid.uuid4()
    chunk_id = uuid.uuid4()
    processor = _FakeProcessor(
        chunks_by_id={ok_doc: [chunk_id]}, fail_ids={bad_doc}
    )
    nodes = ResearchNodes(processor=processor)
    state = _initial(selected_documents=[ok_doc, bad_doc])

    state = _run(nodes.processing_node, state)

    assert state.processed_document_ids == [ok_doc]
    assert state.failed_document_ids == [bad_doc]
    assert state.chunk_ids == [chunk_id]
    assert state.processing_status[ok_doc] == "processed"
    assert state.processing_status[bad_doc] == "failed"
    assert state.budget.processing_operations == 1
    assert state.current_stage == WorkflowStage.EXTRACTING


def test_processing_node_skips_already_processed() -> None:
    doc_id = uuid.uuid4()
    processor = _FakeProcessor(chunks_by_id={doc_id: [uuid.uuid4()]})
    nodes = ResearchNodes(processor=processor)
    state = _initial(selected_documents=[doc_id], processed_document_ids=[doc_id])

    state = _run(nodes.processing_node, state)

    assert state.budget.processing_operations == 0
    assert state.chunk_ids == []


# --- evidence_node -----------------------------------------------------------


class _FakeRetriever:
    def __init__(self, chunks) -> None:
        self._chunks = chunks

    def retrieve(self, query):
        return RetrievalResult(
            query=query, chunks=self._chunks, total_found=len(self._chunks),
            retrieved_at=datetime.now(UTC),
        )


class _FakeClaimExtractor:
    def __init__(self, claims) -> None:
        self._claims = claims

    def extract(self, chunks, query):
        return ClaimExtractionResult(
            query=query, claims=self._claims, total_claims=len(self._claims),
            model_used="fake", extracted_at=datetime.now(UTC),
        )


class _FakeEvidenceExtractor:
    def extract(self, claim, chunks):
        return EvidenceExtractionResult(
            claim_id=claim.claim_id, evidence=[_evidence(claim.claim_id)],
            final_status=EvidenceStatus.SUPPORTED, extracted_at=datetime.now(UTC),
        )


def test_evidence_node_produces_claims_and_evidence() -> None:
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(), document_id=uuid.uuid4(), text="text",
        page_number=1, section=None, score=0.9, document_title=None,
    )
    claim = _claim()
    nodes = ResearchNodes(
        retriever=_FakeRetriever([chunk]),
        claim_extractor=_FakeClaimExtractor([claim]),
        evidence_extractor=_FakeEvidenceExtractor(),
    )
    state = _initial(tasks=[_task("extract", TaskType.EXTRACT)])

    state = _run(nodes.evidence_node, state)

    assert [c.text for c in state.claims] == [claim.text]
    assert len(state.evidence_items) == 1
    assert state.budget.llm_calls == 2  # claims + evidence
    assert state.current_stage == WorkflowStage.SYNTHESIZING


# --- synthesis_node ----------------------------------------------------------


class _FakeLLM:
    def __init__(self, summary: str) -> None:
        self.model = "fake-model"
        self._summary = summary
        self.prompts: list[str] = []

    def complete(self, prompt, response_model):
        self.prompts.append(prompt)
        return response_model(summary=self._summary)


def test_synthesis_node_transitions_to_completed() -> None:
    llm = _FakeLLM("A summary")
    saved: list = []
    nodes = ResearchNodes(llm=llm, summary_saver=lambda rid, summary: saved.append(summary))

    state = _run(nodes.synthesis_node, _initial())

    assert state.current_stage == WorkflowStage.COMPLETED
    assert state.budget.llm_calls == 1
    assert state.completed_at is not None
    assert saved == ["A summary"]
