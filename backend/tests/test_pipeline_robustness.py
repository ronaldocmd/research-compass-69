"""Robustness tests for the orchestrator, LLM adapter and grounding.

Covers the failure scenarios that previously slipped through: a failed node
must stop the graph, an unexpected crash must be recorded, malformed model
output must surface as a typed error, and grounding must tolerate paraphrase
without going soft on hallucination. All services are fakes: no network.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from app.schemas.search import NormalizedSearchResult
from app.services.claims.schemas import Claim
from app.services.grounding.grounder import ground
from app.services.grounding.schemas import GroundingStatus
from app.services.llm.exceptions import InvalidLLMResponseError
from app.services.llm.openai_provider import OpenAILLMProvider, _extract_json_object
from app.services.orchestration.nodes import ResearchNodes
from app.services.orchestration.orchestrator import ResearchOrchestrator
from app.services.planning.schemas import PlanTask, ResearchPlan, TaskStatus, TaskType
from app.services.retrieval.schemas import RetrievalResult
from app.services.workflow.budget_guard import BudgetConfig
from app.services.workflow.retry_handler import RetryPolicy
from app.services.workflow.state import ResearchWorkflowState, WorkflowStage
from app.services.workflow.state_manager import WorkflowStateManager

FAST_RETRY = RetryPolicy(max_attempts=2, base_delay_seconds=0)


def _research():
    return SimpleNamespace(objective="objective", question="question?")


def _task(title, task_type=TaskType.SEARCH) -> PlanTask:
    return PlanTask(
        task_id=uuid.uuid4(), title=title, description=f"{title} desc",
        priority=1, task_type=task_type, status=TaskStatus.PENDING,
    )


def _plan(research_id, *tasks) -> ResearchPlan:
    return ResearchPlan(
        plan_id=uuid.uuid4(), research_id=research_id, tasks=list(tasks),
        created_at=datetime.now(UTC),
    )


def _initial(**updates) -> ResearchWorkflowState:
    return WorkflowStateManager.create_initial_state(uuid.uuid4()).model_copy(update=updates)


class _Planner:
    def __init__(self, plan=None, error: Exception | None = None) -> None:
        self._plan, self._error = plan, error

    async def plan(self, plan_input):
        if self._error:
            raise self._error
        return self._plan


class _SpySearch:
    def __init__(self, error: Exception | None = None, on_call=None) -> None:
        self.calls: list[str] = []
        self._error, self._on_call = error, on_call

    def search(self, query):
        self.calls.append(query)
        if self._on_call:
            self._on_call()
        if self._error:
            raise self._error
        return [NormalizedSearchResult(source="openalex", title=query)]


# --- graph routing -----------------------------------------------------------


def test_planner_failure_with_transient_error_stops_pipeline_as_failed() -> None:
    """A planner that times out (TRANSIENT, not PERMANENT) used to fall through
    to search/synthesis and finish COMPLETED. It must end FAILED, untouched
    downstream."""
    search = _SpySearch()
    nodes = ResearchNodes(
        planner=_Planner(error=asyncio.TimeoutError("llm timeout")),
        research_loader=lambda rid: _research(),
        search=search,
        retry_policy=FAST_RETRY,
    )

    with patch("asyncio.sleep", new_callable=AsyncMock):
        state = asyncio.run(ResearchOrchestrator(nodes=nodes).run(uuid.uuid4()))

    assert state.current_stage == WorkflowStage.FAILED
    assert search.calls == []


def test_search_provider_failure_ends_failed_and_skips_processing() -> None:
    """OpenAlex down for every query: pipeline ends FAILED, nothing processed."""
    processed: list = []
    research_id = uuid.uuid4()
    nodes = ResearchNodes(
        planner=_Planner(plan=_plan(research_id, _task("rare earth AND Brazil"))),
        research_loader=lambda rid: _research(),
        search=_SpySearch(error=ConnectionError("openalex unreachable")),
        processor=lambda doc_id: processed.append(doc_id),
        retry_policy=FAST_RETRY,
    )

    with patch("asyncio.sleep", new_callable=AsyncMock):
        state = asyncio.run(ResearchOrchestrator(nodes=nodes).run(research_id))

    assert state.current_stage == WorkflowStage.FAILED
    assert processed == []
    assert any("openalex unreachable" in e.message for e in state.errors)


# --- orchestrator ------------------------------------------------------------


def test_orchestrator_registers_live_state_while_running() -> None:
    """Status must be readable mid-run, not only after completion."""
    research_id = uuid.uuid4()
    seen_stages: list[WorkflowStage] = []
    holder: dict = {}

    def peek() -> None:
        orch = holder["orch"]
        execution_id = orch._latest_by_research[research_id]
        seen_stages.append(orch._states[execution_id].current_stage)

    nodes = ResearchNodes(
        planner=_Planner(plan=_plan(research_id, _task("q"))),
        research_loader=lambda rid: _research(),
        search=_SpySearch(on_call=peek),
    )
    holder["orch"] = ResearchOrchestrator(nodes=nodes)

    final = asyncio.run(holder["orch"].run(research_id))

    assert seen_stages == [WorkflowStage.SEARCHING]
    assert final.current_stage == WorkflowStage.COMPLETED


def test_orchestrator_records_unexpected_crash_as_failed_state() -> None:
    class _Exploding:
        @property
        def objective(self):
            raise RuntimeError("bug in node")

        question = "q"

    research_id = uuid.uuid4()
    nodes = ResearchNodes(
        planner=_Planner(plan=_plan(research_id, _task("q"))),
        research_loader=lambda rid: _Exploding(),
    )
    orch = ResearchOrchestrator(nodes=nodes)

    state = asyncio.run(orch.run(research_id))

    assert state.current_stage == WorkflowStage.FAILED
    assert "bug in node" in state.errors[-1].message
    assert asyncio.run(orch.get_state_by_research(research_id)).current_stage == WorkflowStage.FAILED


# --- planner persistence -----------------------------------------------------


def test_planner_node_persists_plan_via_saver() -> None:
    research_id = uuid.uuid4()
    plan = _plan(research_id, _task("a"), _task("b"))
    saved: list = []
    nodes = ResearchNodes(
        planner=_Planner(plan=plan), research_loader=lambda rid: _research(),
        plan_saver=saved.append,
    )

    state = asyncio.run(nodes.planner_node(_initial(research_id=research_id)))

    assert saved == [plan]
    assert state.current_stage == WorkflowStage.SEARCHING


def test_planner_node_survives_plan_persistence_failure() -> None:
    research_id = uuid.uuid4()

    def boom(plan):
        raise RuntimeError("db down")

    nodes = ResearchNodes(
        planner=_Planner(plan=_plan(research_id, _task("a"))),
        research_loader=lambda rid: _research(), plan_saver=boom,
        retry_policy=FAST_RETRY,
    )

    state = asyncio.run(nodes.planner_node(_initial(research_id=research_id)))

    assert state.current_stage == WorkflowStage.SEARCHING
    assert len(state.tasks) == 1
    assert any("db down" in e.message for e in state.errors)


# --- processing: oversized / unavailable documents ---------------------------


def test_processing_records_dropped_documents_and_continues() -> None:
    """A document rejected as too large (reason set) is marked failed; the next
    one still gets processed."""
    good, huge = uuid.uuid4(), uuid.uuid4()
    chunk = uuid.uuid4()

    def processor(doc_id):
        if doc_id == huge:
            return SimpleNamespace(chunk_ids=[], reason="storage_rejected: file too large")
        return SimpleNamespace(chunk_ids=[chunk], reason=None)

    nodes = ResearchNodes(processor=processor)
    state = asyncio.run(nodes.processing_node(_initial(selected_documents=[huge, good])))

    assert state.failed_document_ids == [huge]
    assert state.processed_document_ids == [good]
    assert state.processing_status[huge].startswith("failed:storage_rejected")
    assert state.chunk_ids == [chunk]
    assert state.current_stage == WorkflowStage.EXTRACTING


# --- evidence: token limit / duplicate work ----------------------------------


def _empty_retrieval(query: str) -> RetrievalResult:
    return RetrievalResult(
        query=query, chunks=[], total_found=0, retrieved_at=datetime.now(UTC)
    )


def _claim() -> Claim:
    return Claim(
        claim_id=uuid.uuid4(), text="c", chunk_ids=[uuid.uuid4()],
        document_id=uuid.uuid4(), page_number=1, extracted_at=datetime.now(UTC),
    )


def test_evidence_node_retrieves_and_extracts_once_per_distinct_query() -> None:
    retrieved: list[str] = []
    extracted: list[str] = []

    class _Retriever:
        def retrieve(self, query):
            retrieved.append(query)
            return _empty_retrieval(query)

    class _Claims:
        def extract(self, chunks, query):
            extracted.append(query)
            return SimpleNamespace(claims=[_claim()])

    class _Evidence:
        def extract(self, claim, chunks):
            return SimpleNamespace(evidence=[])

    nodes = ResearchNodes(
        retriever=_Retriever(), claim_extractor=_Claims(), evidence_extractor=_Evidence()
    )
    state = _initial(
        research_question="same question",
        tasks=[_task(f"extract {i}", TaskType.EXTRACT) for i in range(3)],
    )

    state = asyncio.run(nodes.evidence_node(state))

    assert retrieved == ["same question"]
    assert extracted == ["same question"]
    assert len(state.claims) == 1


def test_context_overflow_in_claim_extraction_is_recorded_not_fatal() -> None:
    """The LLM rejecting an oversized prompt (permanent provider error) must be
    logged on the state, and the run must still reach validation."""

    class _Retriever:
        def retrieve(self, query):
            return _empty_retrieval(query)

    class _Claims:
        def extract(self, chunks, query):
            raise ValueError("maximum context length exceeded")

    nodes = ResearchNodes(
        retriever=_Retriever(), claim_extractor=_Claims(), evidence_extractor=object(),
        retry_policy=FAST_RETRY,
    )
    state = _initial(research_question="q", tasks=[_task("x", TaskType.EXTRACT)])

    state = asyncio.run(nodes.evidence_node(state))

    assert state.claims == []
    assert state.current_stage == WorkflowStage.VALIDATING
    assert any("maximum context length" in e.message for e in state.errors)


def test_llm_budget_exhaustion_routes_to_budget_exceeded() -> None:
    research_id = uuid.uuid4()
    nodes = ResearchNodes(
        planner=_Planner(plan=_plan(research_id, _task("q"))),
        research_loader=lambda rid: _research(),
        budget_config=BudgetConfig(max_llm_calls=0),
    )

    state = asyncio.run(ResearchOrchestrator(nodes=nodes).run(research_id))

    assert state.current_stage == WorkflowStage.BUDGET_EXCEEDED


# --- selection: batched scoring ----------------------------------------------


def test_selection_scores_candidates_with_one_batch_call() -> None:
    class _Provider:
        def __init__(self) -> None:
            self.batch_calls = 0
            self.single_calls = 0

        def embed(self, text):
            self.single_calls += 1
            return [1.0, 0.0]

        def embed_batch(self, texts):
            self.batch_calls += 1
            return [[1.0, 0.0] if "relevant" in t else [0.0, 1.0] for t in texts]

    provider = _Provider()
    nodes = ResearchNodes(embedding_provider=provider)
    results = [
        NormalizedSearchResult(source="openalex", title="relevant one", doi="10.1/a"),
        NormalizedSearchResult(source="openalex", title="off topic", doi="10.1/b"),
        NormalizedSearchResult(source="openalex", title="relevant two", doi="10.1/c"),
    ]

    state = asyncio.run(
        nodes.selection_node(_initial(search_results=results, research_question="relevant?"))
    )

    assert provider.batch_calls == 1
    assert provider.single_calls == 1  # only the question itself
    assert len(state.selected_documents) == 2
    assert state.selection_stats["discarded_irrelevant"] == 1


def test_selection_falls_back_when_batch_embedding_fails() -> None:
    class _Provider:
        def embed(self, text):
            return [1.0, 0.0]

        def embed_batch(self, texts):
            raise RuntimeError("batch endpoint down")

    nodes = ResearchNodes(embedding_provider=_Provider())
    results = [NormalizedSearchResult(source="openalex", title="a", doi="10.1/a")]

    state = asyncio.run(
        nodes.selection_node(_initial(search_results=results, research_question="q"))
    )

    assert len(state.selected_documents) == 1


# --- LLM adapter: malformed JSON ---------------------------------------------


class _Summary(BaseModel):
    summary: str


def _deepseek_provider(content: str) -> OpenAILLMProvider:
    message = SimpleNamespace(content=content, refusal=None)
    completion = SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: completion))
    )
    return OpenAILLMProvider(model="deepseek/deepseek-chat", client=client)


@pytest.mark.parametrize(
    "content",
    [
        '{"summary": "ok"}',
        '```json\n{"summary": "ok"}\n```',
        'Here you go:\n{"summary": "ok"}\nHope this helps!',
    ],
)
def test_llm_adapter_parses_fenced_or_wrapped_json(content: str) -> None:
    assert _deepseek_provider(content).complete("p", _Summary).summary == "ok"


@pytest.mark.parametrize(
    "content",
    ['{"summary": "cut off', "not json at all", "", '{"wrong_field": 1}'],
)
def test_llm_adapter_raises_typed_error_on_malformed_json(content: str) -> None:
    with pytest.raises(InvalidLLMResponseError):
        _deepseek_provider(content).complete("p", _Summary)


def test_extract_json_object_ignores_braces_inside_strings() -> None:
    assert _extract_json_object('x {"a": "}{", "b": {"c": 1}} y') == '{"a": "}{", "b": {"c": 1}}'


# --- grounding: paraphrase vs hallucination ----------------------------------

_CHUNK = (
    "Rare earth extraction in Brazil increased production and reduced imports "
    "significantly during 2020."
)


def _ground(claim: str, evidence: str = "Rare earth extraction in Brazil increased production"):
    return ground(claim, evidence, _CHUNK, claim_id=uuid.uuid4(), evidence_id=uuid.uuid4())


def test_grounding_accepts_inflected_paraphrase() -> None:
    result = _ground("Rare earth extraction in Brazil increases production and reduces imports")
    assert result.status == GroundingStatus.GROUNDED


def test_grounding_still_rejects_claim_with_unsupported_extra_content() -> None:
    result = _ground(
        "Rare earth extraction in Brazil increased production and permanently "
        "eliminated environmental damage across neighbouring countries"
    )
    assert result.status == GroundingStatus.PARTIALLY_GROUNDED


def test_grounding_still_rejects_wrong_number() -> None:
    assert _ground("Rare earth extraction in Brazil increased production by 95% in 2020").status == (
        GroundingStatus.PARTIALLY_GROUNDED
    )


def test_grounding_rejects_fabricated_evidence() -> None:
    result = _ground("anything", evidence="Lithium mining collapsed in Chile last winter")
    assert result.status == GroundingStatus.UNGROUNDED


# --- plan persistence (real service, SQLite) ---------------------------------


def test_save_plan_persists_tasks_and_replaces_previous_plan() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.base import Base
    from app.models.research import Research
    from app.repositories.research_repository import ResearchRepository
    from app.services.research_plan_service import ResearchPlanService

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, future=True)() as db:
        research = ResearchRepository(db).create(title="t", objective="o", question="q")
        service = ResearchPlanService(db, planner=object())

        service.save_plan(_plan(research.id, _task("first"), _task("second")))
        service.save_plan(_plan(research.id, _task("only")))

        tasks = service.list_tasks(research.id)
        assert [t.title for t in tasks] == ["only"]
        assert isinstance(research, Research)


# --- planner: one corrective retry on malformed model output -----------------


class _SequencedLLM:
    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.prompts: list[str] = []

    def complete(self, prompt, response_model):
        self.prompts.append(prompt)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _plan_input():
    from app.services.planning.schemas import ResearchPlanInput

    return ResearchPlanInput(research_id=uuid.uuid4(), objective="o", question="q")


def test_planner_retries_once_with_feedback_after_malformed_output() -> None:
    from app.services.planning.planner import ResearchPlanner
    from app.services.planning.schemas import PlanTaskDraft, ResearchPlanResponse

    good = ResearchPlanResponse(tasks=[
        PlanTaskDraft(title="t", description="d", priority=1, task_type="SEARCH")
    ])
    llm = _SequencedLLM(InvalidLLMResponseError("tasks.0.description Field required"), good)

    plan = asyncio.run(ResearchPlanner(llm, min_tasks=1, max_tasks=5).plan(_plan_input()))

    assert len(plan.tasks) == 1
    assert len(llm.prompts) == 2
    assert "previous answer was rejected" in llm.prompts[1]
    assert "Field required" in llm.prompts[1]


def test_planner_gives_up_after_second_malformed_output() -> None:
    from app.services.planning.exceptions import InvalidPlanError
    from app.services.planning.planner import ResearchPlanner

    llm = _SequencedLLM(InvalidLLMResponseError("bad"), InvalidLLMResponseError("still bad"))

    with pytest.raises(InvalidPlanError):
        asyncio.run(ResearchPlanner(llm, min_tasks=1, max_tasks=5).plan(_plan_input()))
    assert len(llm.prompts) == 2
