"""Individual node tests (RDA-034).

Every service is replaced with a fake: no real LLM/search/DB calls.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from app.schemas.search import NormalizedSearchResult
from app.services.claims.schemas import Claim, ClaimExtractionResult
from app.services.confidence.schemas import ConfidenceLevel, ConfidenceScore, ScoredClaim
from app.services.evidence.schemas import Evidence, EvidenceExtractionResult, EvidenceStatus
from app.services.orchestration.nodes import ResearchNodes, SynthesisResponse
from app.services.planning.schemas import PlanTask, ResearchPlan, TaskStatus, TaskType
from app.services.provenance.schemas import DocumentSource, ProvenanceChain, ProvenanceLink
from app.services.retrieval.schemas import RetrievedChunk, RetrievalResult
from app.services.validation.schemas import ValidationResult, ValidationStatus
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


class _RelevanceEmbeddingProvider:
    """Fake provider: embeds text into a vector whose similarity to the
    question vector is high for relevant text and low for irrelevant text."""

    def __init__(self) -> None:
        self._question = [1.0, 0.0]

    def embed(self, text: str) -> list[float]:
        lowered = text.lower()
        if "llm" in lowered or "language model" in lowered:
            return [1.0, 0.0]  # highly relevant
        if "education" in lowered:
            return [0.6, 0.8]  # partially relevant
        return [0.0, 1.0]  # irrelevant


def test_selection_node_filters_by_relevance() -> None:
    """RDA-058: with an embedding provider and a research question, results
    below SELECTION_MIN_SCORE are dropped for irrelevance."""
    nodes = ResearchNodes(
        max_documents=10, embedding_provider=_RelevanceEmbeddingProvider()
    )
    results = [
        NormalizedSearchResult(source="openalex", title="LLMs in education", doi="10.1/a"),
        NormalizedSearchResult(source="openalex", title="A study about gardening", doi="10.2/b"),
        NormalizedSearchResult(source="openalex", title="Large language models", doi="10.3/c"),
    ]
    state = _initial(
        search_results=results, research_question="What is the impact of LLMs on education?"
    )

    state = _run(nodes.selection_node, state)

    assert len(state.selected_documents) == 2
    assert state.selection_stats["search_results"] == 3
    assert state.selection_stats["selected"] == 2
    assert state.selection_stats["discarded_irrelevant"] == 1


def test_selection_node_without_question_selects_all() -> None:
    """RDA-058: without a research question the relevance filter is skipped
    and all results are selected (backwards compatible)."""
    nodes = ResearchNodes(
        max_documents=10, embedding_provider=_RelevanceEmbeddingProvider()
    )
    results = [
        NormalizedSearchResult(source="openalex", title="LLMs in education", doi="10.1/a"),
        NormalizedSearchResult(source="openalex", title="A study about gardening", doi="10.2/b"),
    ]
    state = _initial(search_results=results)

    state = _run(nodes.selection_node, state)

    assert len(state.selected_documents) == 2
    assert state.selection_stats["discarded_irrelevant"] == 0


# --- processing_node ---------------------------------------------------------


class _FakeProcessor:
    def __init__(self, *, chunks_by_id=None, fail_ids=None, unavailable_ids=None) -> None:
        self._chunks = chunks_by_id or {}
        self._fail = fail_ids or set()
        self._unavailable = unavailable_ids or set()

    def __call__(self, doc_id):
        if doc_id in self._fail:
            raise RuntimeError("boom")
        if doc_id in self._unavailable:
            from app.services.orchestration.wiring import ProcessResult
            return ProcessResult(reason="download_failed: html")
        return self._chunks.get(doc_id, [])


def test_selection_processing_separates_relevance_from_downloadability() -> None:
    """RDA-058 FASE 9: reproduces the RDA-057 scenario where the index was
    polluted with off-topic PDFs while relevant HTML sources were dropped.

    Groups:
      A relevant + PDF, B relevant + HTML, C irrelevant + PDF,
      D irrelevant + HTML, E relevant + PDF (control).
    Selection must keep A, B, E (relevance) and drop C, D (irrelevance);
    processing must record B as unavailable (HTML), not as irrelevant.
    """
    from app.services.orchestration.wiring import ProcessResult

    class _GroupProcessor:
        def __init__(self, unavailable_ids) -> None:
            self._unavailable = unavailable_ids

        def __call__(self, doc_id):
            if doc_id in self._unavailable:
                return ProcessResult(reason="storage_rejected: html")
            return [uuid.uuid4()]

    results = [
        NormalizedSearchResult(source="openalex", title="LLMs in education", doi="10.1/a"),  # A
        NormalizedSearchResult(source="openalex", title="LLMs in education full text", doi="10.2/b"),  # B
        NormalizedSearchResult(source="openalex", title="Gardening techniques", doi="10.3/c"),  # C
        NormalizedSearchResult(source="openalex", title="Cooking recipes", doi="10.4/d"),  # D
        NormalizedSearchResult(source="openalex", title="Large language models review", doi="10.5/e"),  # E
    ]
    nodes = ResearchNodes(
        max_documents=10, embedding_provider=_RelevanceEmbeddingProvider()
    )
    state = _initial(
        search_results=results,
        research_question="What is the impact of LLMs on education?",
    )
    state = _run(nodes.selection_node, state)

    # A, B, E are relevant -> selected; C, D irrelevant -> dropped.
    assert len(state.selected_documents) == 3
    assert state.selection_stats["discarded_irrelevant"] == 2

    # B (relevant but HTML) is unavailable at processing time.
    selected_ids = state.selected_documents
    b_id = selected_ids[1]
    processor = _GroupProcessor(unavailable_ids={b_id})
    nodes2 = ResearchNodes(processor=processor)
    state = _run(nodes2.processing_node, state)

    assert state.processing_status[b_id].startswith("failed:storage_rejected")
    assert state.selection_stats["processed"] == 2
    assert state.selection_stats["failed"] == 1


def test_retrieval_query_uses_research_question() -> None:
    """RDA-058: the retrieval query is built from the research question, not
    the generic EXTRACT task title."""
    nodes = ResearchNodes()
    task = _task("Extract key findings from the selected studies", TaskType.EXTRACT)
    state = _initial(
        research_question="What is the impact of LLMs on education?",
        tasks=[task],
    )
    query = nodes._retrieval_query(state, task)
    assert "impact of llms on education" in query.lower()


def test_retrieval_query_falls_back_to_task_title() -> None:
    """RDA-058: without a research question the query falls back to the task
    title (backwards compatible)."""
    nodes = ResearchNodes()
    task = _task("Extract key findings", TaskType.EXTRACT)
    state = _initial(tasks=[task])
    assert nodes._retrieval_query(state, task) == "Extract key findings"


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


def test_processing_node_records_unavailability_reason() -> None:
    """RDA-058: a document dropped for technical unavailability (e.g. HTML)
    is recorded distinctly from a processed document, so downloadability is
    not silently conflated with relevance."""
    ok_doc = uuid.uuid4()
    html_doc = uuid.uuid4()
    chunk_id = uuid.uuid4()
    processor = _FakeProcessor(
        chunks_by_id={ok_doc: [chunk_id]}, unavailable_ids={html_doc}
    )
    nodes = ResearchNodes(processor=processor)
    state = _initial(selected_documents=[ok_doc, html_doc])

    state = _run(nodes.processing_node, state)

    assert state.processed_document_ids == [ok_doc]
    assert state.failed_document_ids == [html_doc]
    assert state.chunk_ids == [chunk_id]
    assert state.processing_status[ok_doc] == "processed"
    assert state.processing_status[html_doc].startswith("failed:download_failed")
    assert state.selection_stats["processed"] == 1
    assert state.selection_stats["failed"] == 1
    assert state.selection_stats["chunk_count"] == 1


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
    assert state.current_stage == WorkflowStage.VALIDATING


def test_evidence_node_stores_retrieved_chunks() -> None:
    """RDA-061: the evidence node records the retrieved chunks (with their
    retrieval score) so the validation node can rebuild provenance and pass
    retrieval scores to the confidence scorer."""
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

    assert [c.chunk_id for c in state.retrieved_chunks] == [chunk.chunk_id]
    assert state.retrieved_chunks[0].score == 0.9


# --- validation_node ---------------------------------------------------------


class _FakeValidator:
    def validate(self, claim, evidence):
        return ValidationResult(
            validation_id=uuid.uuid4(), claim_id=claim.claim_id,
            evidence_id=evidence.evidence_id, status=ValidationStatus.SUPPORTED,
            reasoning="supported", validated_at=datetime.now(UTC), model_used="fake",
        )


class _FakeConfidenceScorer:
    def score_claim(self, claim, evidence, retrieval_scores=None):
        return ScoredClaim(
            claim=claim, evidence=evidence,
            confidence=ConfidenceScore(
                level=ConfidenceLevel.HIGH, score=0.9, reasoning="ok", factors={}
            ),
            scored_at=datetime.now(UTC),
        )


class _FakeProvenanceResolver:
    def resolve(self, claim, evidence, chunk, document_source):
        return ProvenanceChain(
            claim_id=claim.claim_id,
            chain=[
                ProvenanceLink(level="claim", id=str(claim.claim_id), description=claim.text),
                ProvenanceLink(level="evidence", id=str(evidence.evidence_id), description=evidence.text),
            ],
            resolved_at=datetime.now(UTC), is_complete=False,
        )


def _validation_state() -> ResearchWorkflowState:
    claim = _claim()
    evidence = _evidence(claim.claim_id)
    chunk = RetrievedChunk(
        chunk_id=evidence.chunk_id, document_id=evidence.document_id, text="text",
        page_number=1, section=None, score=0.9, document_title=None,
    )
    return _initial(
        claims=[claim], evidence_items=[evidence], retrieved_chunks=[chunk],
    )


def test_validation_node_produces_validation_provenance_confidence() -> None:
    """RDA-061: the validation node wires the orphan services, producing
    validation results, provenance chains and scored claims, then transitions
    to synthesis."""
    nodes = ResearchNodes(
        validator=_FakeValidator(),
        provenance_resolver=_FakeProvenanceResolver(),
        confidence_scorer=_FakeConfidenceScorer(),
        document_resolver=lambda doc_id, chunk: DocumentSource(
            document_id=doc_id, title="Doc", url="https://x", doi="10.1/x",
            page_number=chunk.page_number, chunk_id=chunk.chunk_id,
        ),
    )
    state = _validation_state()

    state = _run(nodes.validation_node, state)

    assert len(state.validation_results) == 1
    assert len(state.provenance_chains) == 1
    assert len(state.scored_claims) == 1
    assert state.scored_claims[0].confidence.level == ConfidenceLevel.HIGH
    assert state.current_stage == WorkflowStage.SYNTHESIZING


def test_validation_node_skips_when_services_missing() -> None:
    """RDA-061: without the orphan services the validation node is a no-op
    that still transitions to synthesis (backwards compatible)."""
    nodes = ResearchNodes()
    state = _validation_state()

    state = _run(nodes.validation_node, state)

    assert state.validation_results == []
    assert state.provenance_chains == []
    assert state.scored_claims == []
    assert state.current_stage == WorkflowStage.SYNTHESIZING


def test_validation_node_persists_state() -> None:
    """RDA-061: when a persister is wired, the validation node persists the
    chain before transitioning to synthesis."""
    persisted: list = []
    nodes = ResearchNodes(
        validator=_FakeValidator(),
        provenance_resolver=_FakeProvenanceResolver(),
        confidence_scorer=_FakeConfidenceScorer(),
        document_resolver=lambda doc_id, chunk: DocumentSource(
            document_id=doc_id, title="Doc", url="https://x", doi="10.1/x",
            page_number=chunk.page_number, chunk_id=chunk.chunk_id,
        ),
        evidence_persister=lambda state: persisted.append(state),
    )
    state = _validation_state()

    state = _run(nodes.validation_node, state)

    assert len(persisted) == 1
    assert persisted[0].scored_claims[0].claim.claim_id == state.claims[0].claim_id


class _FailingValidator:
    def validate(self, claim, evidence):
        raise RuntimeError("validator unavailable")


def test_validation_node_records_unsupported_on_validator_failure() -> None:
    """RDA-062: when the independent validator cannot run, the validation node
    records a conservative UNSUPPORTED result so the claim is not presented as
    a verified finding."""
    nodes = ResearchNodes(
        validator=_FailingValidator(),
        provenance_resolver=_FakeProvenanceResolver(),
        confidence_scorer=_FakeConfidenceScorer(),
        document_resolver=lambda doc_id, chunk: DocumentSource(
            document_id=doc_id, title="Doc", url="https://x", doi="10.1/x",
            page_number=chunk.page_number, chunk_id=chunk.chunk_id,
        ),
    )
    state = _validation_state()

    state = _run(nodes.validation_node, state)

    assert len(state.validation_results) == 1
    assert state.validation_results[0].status == ValidationStatus.UNSUPPORTED
    assert state.validation_results[0].claim_id == state.claims[0].claim_id
    assert state.current_stage == WorkflowStage.SYNTHESIZING
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
    claim = _claim()
    scored = ScoredClaim(
        claim=claim, evidence=[],
        confidence=ConfidenceScore(
            level=ConfidenceLevel.HIGH, score=0.9, reasoning="ok", factors={}
        ),
        scored_at=datetime.now(UTC),
    )

    state = _run(
        nodes.synthesis_node,
        _initial(
            claims=[claim],
            scored_claims=[scored],
            validation_results=[
                ValidationResult(
                    validation_id=uuid.uuid4(), claim_id=claim.claim_id,
                    evidence_id=uuid.uuid4(), status=ValidationStatus.SUPPORTED,
                    reasoning="ok", validated_at=datetime.now(UTC), model_used="fake",
                )
            ],
        ),
    )

    assert state.current_stage == WorkflowStage.COMPLETED
    assert state.budget.llm_calls == 1
    assert state.completed_at is not None
    assert saved == ["A summary"]
    assert state.synthesis_stats["included"] == 1


def test_synthesis_node_filters_low_confidence_claims() -> None:
    """RDA-061: claims below SYNTHESIS_MIN_CONFIDENCE are excluded from the
    summary so unsupported statements are not presented as verified facts."""
    llm = _FakeLLM("A summary")
    saved: list = []
    nodes = ResearchNodes(llm=llm, summary_saver=lambda rid, summary: saved.append(summary))
    high_claim = _claim().model_copy(update={"text": "high confidence claim"})
    low_claim = _claim().model_copy(update={"text": "low confidence claim"})
    scored = [
        ScoredClaim(
            claim=high_claim, evidence=[],
            confidence=ConfidenceScore(
                level=ConfidenceLevel.HIGH, score=0.9, reasoning="ok", factors={}
            ),
            scored_at=datetime.now(UTC),
        ),
        ScoredClaim(
            claim=low_claim, evidence=[],
            confidence=ConfidenceScore(
                level=ConfidenceLevel.LOW, score=0.2, reasoning="weak", factors={}
            ),
            scored_at=datetime.now(UTC),
        ),
    ]

    state = _run(
        nodes.synthesis_node,
        _initial(
            claims=[high_claim, low_claim],
            scored_claims=scored,
            validation_results=[
                ValidationResult(
                    validation_id=uuid.uuid4(), claim_id=high_claim.claim_id,
                    evidence_id=uuid.uuid4(), status=ValidationStatus.SUPPORTED,
                    reasoning="ok", validated_at=datetime.now(UTC), model_used="fake",
                ),
                ValidationResult(
                    validation_id=uuid.uuid4(), claim_id=low_claim.claim_id,
                    evidence_id=uuid.uuid4(), status=ValidationStatus.UNSUPPORTED,
                    reasoning="no", validated_at=datetime.now(UTC), model_used="fake",
                ),
            ],
        ),
    )

    assert state.current_stage == WorkflowStage.COMPLETED
    assert state.synthesis_stats["total_claims"] == 2
    assert state.synthesis_stats["included"] == 1
    assert state.synthesis_stats["excluded_low_confidence"] == 1
    # Only the HIGH claim is in the prompt.
    assert high_claim.text in llm.prompts[0]
    assert low_claim.text not in llm.prompts[0]


def test_synthesis_node_skips_when_no_supported_claims() -> None:
    """RDA-061: when every claim is below the confidence threshold, synthesis
    is skipped and no summary is fabricated."""
    llm = _FakeLLM("A summary")
    saved: list = []
    nodes = ResearchNodes(llm=llm, summary_saver=lambda rid, summary: saved.append(summary))
    claim = _claim()
    scored = ScoredClaim(
        claim=claim, evidence=[],
        confidence=ConfidenceScore(
            level=ConfidenceLevel.LOW, score=0.1, reasoning="weak", factors={}
        ),
        scored_at=datetime.now(UTC),
    )

    state = _run(nodes.synthesis_node, _initial(claims=[claim], scored_claims=[scored]))

    assert state.current_stage == WorkflowStage.COMPLETED
    assert state.budget.llm_calls == 0
    assert saved == []
    assert state.synthesis_stats["included"] == 0
    assert any("minimum confidence" in e.message for e in state.errors)


def test_synthesis_node_skips_when_no_claims() -> None:
    """Quality gate (RDA-058): with no claims the synthesis must not fabricate
    a summary from empty context; it records a warning and completes."""
    llm = _FakeLLM("A summary")
    saved: list = []
    nodes = ResearchNodes(llm=llm, summary_saver=lambda rid, summary: saved.append(summary))

    state = _run(nodes.synthesis_node, _initial())

    assert state.current_stage == WorkflowStage.COMPLETED
    assert state.budget.llm_calls == 0
    assert saved == []
    assert state.completed_at is not None
    assert any("Synthesis skipped" in e.message for e in state.errors)



# --- RDA-062: validation gate on synthesis -----------------------------------


def _supported_validation(claim_id) -> ValidationResult:
    return ValidationResult(
        validation_id=uuid.uuid4(), claim_id=claim_id, evidence_id=uuid.uuid4(),
        status=ValidationStatus.SUPPORTED, reasoning="ok",
        validated_at=datetime.now(UTC), model_used="fake",
    )


def _unsupported_validation(claim_id) -> ValidationResult:
    return ValidationResult(
        validation_id=uuid.uuid4(), claim_id=claim_id, evidence_id=uuid.uuid4(),
        status=ValidationStatus.UNSUPPORTED, reasoning="no",
        validated_at=datetime.now(UTC), model_used="fake",
    )


def test_synthesis_excludes_high_confidence_without_supported_validation() -> None:
    """RDA-062: a HIGH-confidence claim with no SUPPORTED validation must not
    reach the summary. Confidence alone (extractor status + retrieval) is not
    enough to present a claim as a verified finding."""
    llm = _FakeLLM("A summary")
    saved: list = []
    nodes = ResearchNodes(llm=llm, summary_saver=lambda rid, summary: saved.append(summary))
    claim = _claim()
    scored = ScoredClaim(
        claim=claim, evidence=[],
        confidence=ConfidenceScore(
            level=ConfidenceLevel.HIGH, score=0.9, reasoning="ok", factors={}
        ),
        scored_at=datetime.now(UTC),
    )

    state = _run(
        nodes.synthesis_node,
        _initial(claims=[claim], scored_claims=[scored]),
    )

    assert state.current_stage == WorkflowStage.COMPLETED
    assert state.budget.llm_calls == 0
    assert saved == []
    assert state.synthesis_stats["included"] == 0


def test_synthesis_excludes_high_confidence_with_unsupported_validation() -> None:
    """RDA-062: a HIGH-confidence claim whose independent validation is
    UNSUPPORTED must be excluded from the summary."""
    llm = _FakeLLM("A summary")
    saved: list = []
    nodes = ResearchNodes(llm=llm, summary_saver=lambda rid, summary: saved.append(summary))
    claim = _claim()
    scored = ScoredClaim(
        claim=claim, evidence=[],
        confidence=ConfidenceScore(
            level=ConfidenceLevel.HIGH, score=0.9, reasoning="ok", factors={}
        ),
        scored_at=datetime.now(UTC),
    )

    state = _run(
        nodes.synthesis_node,
        _initial(
            claims=[claim],
            scored_claims=[scored],
            validation_results=[_unsupported_validation(claim.claim_id)],
        ),
    )

    assert state.current_stage == WorkflowStage.COMPLETED
    assert state.budget.llm_calls == 0
    assert saved == []
    assert state.synthesis_stats["included"] == 0


def test_synthesis_includes_medium_confidence_with_supported_validation() -> None:
    """RDA-062: a MEDIUM-confidence claim with a SUPPORTED validation is
    included (MEDIUM is the SYNTHESIS_MIN_CONFIDENCE threshold)."""
    llm = _FakeLLM("A summary")
    saved: list = []
    nodes = ResearchNodes(llm=llm, summary_saver=lambda rid, summary: saved.append(summary))
    claim = _claim()
    scored = ScoredClaim(
        claim=claim, evidence=[],
        confidence=ConfidenceScore(
            level=ConfidenceLevel.MEDIUM, score=0.6, reasoning="ok", factors={}
        ),
        scored_at=datetime.now(UTC),
    )

    state = _run(
        nodes.synthesis_node,
        _initial(
            claims=[claim],
            scored_claims=[scored],
            validation_results=[_supported_validation(claim.claim_id)],
        ),
    )

    assert state.current_stage == WorkflowStage.COMPLETED
    assert state.budget.llm_calls == 1
    assert saved == ["A summary"]
    assert state.synthesis_stats["included"] == 1



# --- RDA-062 Phase 28: quality gates -----------------------------------------


def _scored(claim, level, score) -> ScoredClaim:
    return ScoredClaim(
        claim=claim, evidence=[],
        confidence=ConfidenceScore(
            level=level, score=score, reasoning="ok", factors={}
        ),
        scored_at=datetime.now(UTC),
    )


def test_quality_gate_case1_no_supported_claims_no_summary() -> None:
    """Case 1: 0 supported claims -> no factual summary is produced."""
    llm = _FakeLLM("A summary")
    saved: list = []
    nodes = ResearchNodes(llm=llm, summary_saver=lambda rid, summary: saved.append(summary))
    claim = _claim()
    state = _run(
        nodes.synthesis_node,
        _initial(
            claims=[claim],
            scored_claims=[_scored(claim, ConfidenceLevel.LOW, 0.1)],
            validation_results=[_unsupported_validation(claim.claim_id)],
        ),
    )
    assert state.current_stage == WorkflowStage.COMPLETED
    assert state.budget.llm_calls == 0
    assert saved == []
    assert state.synthesis_stats["included"] == 0


def test_quality_gate_case2_only_low_claims_no_summary() -> None:
    """Case 2: only LOW-confidence claims -> no normal factual summary."""
    llm = _FakeLLM("A summary")
    saved: list = []
    nodes = ResearchNodes(llm=llm, summary_saver=lambda rid, summary: saved.append(summary))
    claim = _claim()
    state = _run(
        nodes.synthesis_node,
        _initial(
            claims=[claim],
            scored_claims=[_scored(claim, ConfidenceLevel.LOW, 0.2)],
            validation_results=[_supported_validation(claim.claim_id)],
        ),
    )
    assert state.current_stage == WorkflowStage.COMPLETED
    assert state.budget.llm_calls == 0
    assert saved == []
    assert state.synthesis_stats["included"] == 0


def test_quality_gate_case3_contradicted_claim_excluded() -> None:
    """Case 3: a contradicted claim (UNSUPPORTED validation) is excluded from
    the summary even when it has HIGH confidence; the supported claim is kept."""
    llm = _FakeLLM("A summary")
    saved: list = []
    nodes = ResearchNodes(llm=llm, summary_saver=lambda rid, summary: saved.append(summary))
    supported_claim = _claim().model_copy(update={"text": "supported finding"})
    contradicted_claim = _claim().model_copy(update={"text": "contradicted finding"})
    state = _run(
        nodes.synthesis_node,
        _initial(
            claims=[supported_claim, contradicted_claim],
            scored_claims=[
                _scored(supported_claim, ConfidenceLevel.HIGH, 0.9),
                _scored(contradicted_claim, ConfidenceLevel.HIGH, 0.9),
            ],
            validation_results=[
                _supported_validation(supported_claim.claim_id),
                _unsupported_validation(contradicted_claim.claim_id),
            ],
        ),
    )
    assert state.current_stage == WorkflowStage.COMPLETED
    assert state.synthesis_stats["included"] == 1
    assert supported_claim.text in llm.prompts[0]
    assert contradicted_claim.text not in llm.prompts[0]


def test_quality_gate_case4_partially_supported_excluded() -> None:
    """Case 4: a partially-supported claim (PARTIALLY_SUPPORTED validation) is
    not presented as a verified finding; only SUPPORTED claims reach summary."""
    llm = _FakeLLM("A summary")
    saved: list = []
    nodes = ResearchNodes(llm=llm, summary_saver=lambda rid, summary: saved.append(summary))
    claim = _claim()
    state = _run(
        nodes.synthesis_node,
        _initial(
            claims=[claim],
            scored_claims=[_scored(claim, ConfidenceLevel.MEDIUM, 0.6)],
            validation_results=[
                ValidationResult(
                    validation_id=uuid.uuid4(), claim_id=claim.claim_id,
                    evidence_id=uuid.uuid4(),
                    status=ValidationStatus.PARTIALLY_SUPPORTED,
                    reasoning="partial", validated_at=datetime.now(UTC),
                    model_used="fake",
                )
            ],
        ),
    )
    assert state.current_stage == WorkflowStage.COMPLETED
    assert state.budget.llm_calls == 0
    assert saved == []
    assert state.synthesis_stats["included"] == 0


def test_quality_gate_case5_strongly_supported_summary_allowed() -> None:
    """Case 5: strongly supported claims -> summary is produced."""
    llm = _FakeLLM("A summary")
    saved: list = []
    nodes = ResearchNodes(llm=llm, summary_saver=lambda rid, summary: saved.append(summary))
    claim = _claim()
    state = _run(
        nodes.synthesis_node,
        _initial(
            claims=[claim],
            scored_claims=[_scored(claim, ConfidenceLevel.HIGH, 0.9)],
            validation_results=[_supported_validation(claim.claim_id)],
        ),
    )
    assert state.current_stage == WorkflowStage.COMPLETED
    assert state.budget.llm_calls == 1
    assert saved == ["A summary"]
    assert state.synthesis_stats["included"] == 1
