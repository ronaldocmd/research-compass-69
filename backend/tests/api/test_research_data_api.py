"""Integration tests for /documents, /claims, /run and /status.

Real FastAPI app + in-memory SQLite; only the workflow nodes are faked.
"""

import asyncio
import uuid
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints import run as run_module
from app.api.v1.endpoints.run import _nodes_factory, _orchestrator
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.document import Document
from app.models.research import Research
from app.models.evidence_chain import (
    ClaimRecord,
    ConfidenceRecord,
    EvidenceRecord,
    ValidationRecord,
)
from app.services.confidence.schemas import ConfidenceLevel
from app.services.evidence.schemas import EvidenceStatus
from app.services.orchestration.nodes import ResearchNodes
from app.services.orchestration.orchestrator import ResearchOrchestrator
from app.services.validation.schemas import ValidationStatus
from app.services.workflow.state import WorkflowStage

BASE = f"{settings.API_V1_PREFIX}/researches"
NOW = datetime.now(UTC)


@pytest.fixture
def env() -> Generator[tuple[TestClient, sessionmaker[Session], object], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory: sessionmaker[Session] = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )

    def override_get_db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    orchestrator = ResearchOrchestrator()
    app.dependency_overrides[_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_db] = override_get_db
    run_module._running.clear()
    with TestClient(app) as client:
        yield client, factory, engine
    app.dependency_overrides.clear()
    run_module._running.clear()
    engine.dispose()


def _create_research(client: TestClient) -> str:
    resp = client.post(
        BASE,
        json={"title": "Terras raras", "objective": "Mapear", "question": "Qual o cenário?"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _seed_chain(factory, research_id: str, n_claims: int) -> list[uuid.UUID]:
    """Insert ``n_claims`` claims, each with 2 evidence, 1-2 validations and a score."""
    rid = uuid.UUID(research_id)
    claim_ids = []
    with factory() as db:
        doc = Document(
            id=uuid.uuid4(), research_id=rid, source="openalex", title="Paper A",
            authors=["X"], document_metadata={},
        )
        db.add(doc)
        db.commit()
        for i in range(n_claims):
            claim_id = uuid.uuid4()
            claim_ids.append(claim_id)
            db.add(ClaimRecord(
                claim_id=claim_id, research_id=rid, text=f"claim {i}",
                document_id=doc.id, page_number=3, chunk_ids=[], extracted_at=NOW,
            ))
            db.flush()
            evidence_ids = []
            for j in range(2):
                evidence_id = uuid.uuid4()
                evidence_ids.append(evidence_id)
                db.add(EvidenceRecord(
                    evidence_id=evidence_id, research_id=rid, claim_id=claim_id,
                    text=f"evidence {i}.{j}", document_id=doc.id, page_number=3,
                    status=EvidenceStatus.SUPPORTED, extracted_at=NOW,
                ))
            statuses = (
                [ValidationStatus.UNSUPPORTED, ValidationStatus.SUPPORTED]
                if i % 2 == 0 else [ValidationStatus.UNSUPPORTED]
            )
            for evidence_id, status in zip(evidence_ids, statuses):
                db.add(ValidationRecord(
                    validation_id=uuid.uuid4(), research_id=rid, claim_id=claim_id,
                    evidence_id=evidence_id, status=status, reasoning="r",
                    validated_at=NOW, model_used="m",
                ))
            db.add(ConfidenceRecord(
                confidence_id=uuid.uuid4(), research_id=rid, claim_id=claim_id,
                level=ConfidenceLevel.HIGH, score=0.9, reasoning="r", factors={},
                scored_at=NOW,
            ))
        db.commit()
    return claim_ids


# --- /documents --------------------------------------------------------------


def test_documents_lists_persisted_documents(env) -> None:
    client, factory, _ = env
    research_id = _create_research(client)
    with factory() as db:
        for i in range(3):
            db.add(Document(
                id=uuid.uuid4(), research_id=uuid.UUID(research_id), source="openalex",
                title=f"Doc {i}", authors=[], document_metadata={"k": i},
                storage_path="/internal/path.pdf",
            ))
        db.commit()

    resp = client.get(f"{BASE}/{research_id}/documents")

    assert resp.status_code == 200
    body = resp.json()
    assert {d["title"] for d in body} == {"Doc 0", "Doc 1", "Doc 2"}
    assert all(d["metadata"] is not None for d in body)
    # Internal storage details must not leak through the API.
    assert all("storage_path" not in d for d in body)


def test_documents_supports_pagination(env) -> None:
    client, factory, _ = env
    research_id = _create_research(client)
    with factory() as db:
        for i in range(5):
            db.add(Document(
                id=uuid.uuid4(), research_id=uuid.UUID(research_id), source="openalex",
                title=f"Doc {i}", authors=[], document_metadata={},
            ))
        db.commit()

    page = client.get(f"{BASE}/{research_id}/documents", params={"limit": 2, "offset": 4})

    assert page.status_code == 200
    assert len(page.json()) == 1
    assert client.get(f"{BASE}/{research_id}/documents", params={"limit": 0}).status_code == 422


def test_documents_unknown_research_is_404(env) -> None:
    client, _, _ = env
    assert client.get(f"{BASE}/{uuid.uuid4()}/documents").status_code == 404


# --- /claims -----------------------------------------------------------------


def test_claims_empty_research_returns_empty_list(env) -> None:
    client, _, _ = env
    research_id = _create_research(client)

    resp = client.get(f"{BASE}/{research_id}/claims")

    assert resp.status_code == 200
    assert resp.json() == []
    assert resp.headers["X-Total-Count"] == "0"


def test_claims_match_frontend_contract(env) -> None:
    client, factory, _ = env
    research_id = _create_research(client)
    claim_ids = _seed_chain(factory, research_id, n_claims=2)

    resp = client.get(f"{BASE}/{research_id}/claims")

    assert resp.status_code == 200
    first, second = resp.json()
    # ``id`` must be the claim UUID string (the frontend calls id.slice()), not
    # the integer surrogate key.
    assert first["id"] == str(claim_ids[0])
    assert isinstance(first["id"], str)
    assert first["confidence"] == 0.9
    assert first["document_title"] == "Paper A"
    assert len(first["evidence"]) == 2
    assert first["evidence"][0]["document_title"] == "Paper A"
    # One SUPPORTED validation makes the claim a finding, even next to an
    # UNSUPPORTED one; a claim with only UNSUPPORTED stays unsupported.
    assert first["validation_status"] == "supported"
    assert second["validation_status"] == "unsupported"


def test_claims_query_count_does_not_grow_with_claims(env) -> None:
    """Guard against N+1: 40 claims must cost the same number of queries as 2."""
    client, factory, engine = env
    small = _create_research(client)
    large = _create_research(client)
    _seed_chain(factory, small, n_claims=2)
    _seed_chain(factory, large, n_claims=40)

    def count_queries(research_id: str) -> int:
        statements: list[str] = []

        def before(conn, cursor, statement, *args):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", before)
        try:
            assert client.get(f"{BASE}/{research_id}/claims").status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", before)
        return len(statements)

    assert count_queries(large) == count_queries(small)


def test_claims_pagination_and_total_header(env) -> None:
    client, factory, _ = env
    research_id = _create_research(client)
    _seed_chain(factory, research_id, n_claims=5)

    resp = client.get(f"{BASE}/{research_id}/claims", params={"limit": 2, "offset": 3})

    assert resp.status_code == 200
    assert len(resp.json()) == 2
    assert resp.headers["X-Total-Count"] == "5"


def test_claims_unknown_research_is_404(env) -> None:
    client, _, _ = env
    assert client.get(f"{BASE}/{uuid.uuid4()}/claims").status_code == 404


# --- /run and /status --------------------------------------------------------


def _use_nodes(nodes_builder) -> None:
    app.dependency_overrides[_nodes_factory] = lambda: (lambda db, rid: nodes_builder())


def test_run_then_status_reports_same_execution(env) -> None:
    client, _, _ = env
    research_id = _create_research(client)
    _use_nodes(ResearchNodes)

    run = client.post(f"{BASE}/{research_id}/run")
    status_resp = client.get(f"{BASE}/{research_id}/status")

    assert run.status_code == 200
    assert run.json()["current_stage"] == "COMPLETED"
    assert status_resp.status_code == 200
    assert status_resp.json()["execution_id"] == run.json()["execution_id"]
    assert status_resp.json()["stage"] == "COMPLETED"


def test_run_sets_started_and_completed_timestamps(env) -> None:
    client, factory, _ = env
    research_id = _create_research(client)
    _use_nodes(ResearchNodes)

    client.post(f"{BASE}/{research_id}/run")
    with factory() as db:
        research = db.get(Research, uuid.UUID(research_id))
        assert research.started_at is not None
        assert research.completed_at is not None


def test_run_unknown_research_is_404_and_status_is_404(env) -> None:
    client, _, _ = env
    unknown = uuid.uuid4()
    assert client.post(f"{BASE}/{unknown}/run").status_code == 404
    assert client.get(f"{BASE}/{unknown}/status").status_code == 404


def test_run_failure_is_reported_as_failed_state_not_500(env) -> None:
    """A node crashing unexpectedly must yield a FAILED state, not a 500."""
    client, _, _ = env
    research_id = _create_research(client)

    class _Boom:
        @property
        def objective(self):
            raise RuntimeError("bug")

        question = "q"

    class _Planner:
        async def plan(self, plan_input):
            raise AssertionError("not reached")

    _use_nodes(lambda: ResearchNodes(planner=_Planner(), research_loader=lambda rid: _Boom()))

    run = client.post(f"{BASE}/{research_id}/run")

    assert run.status_code == 200
    assert run.json()["current_stage"] == "FAILED"
    assert client.get(f"{BASE}/{research_id}/status").json()["stage"] == "FAILED"


def test_concurrent_run_for_same_research_is_rejected_with_409(env) -> None:
    client, _, _ = env
    research_id = _create_research(client)
    _use_nodes(ResearchNodes)
    run_module._running.add(uuid.UUID(research_id))

    resp = client.post(f"{BASE}/{research_id}/run")

    assert resp.status_code == 409


def test_run_releases_lock_so_research_can_be_rerun(env) -> None:
    client, _, _ = env
    research_id = _create_research(client)
    _use_nodes(ResearchNodes)

    assert client.post(f"{BASE}/{research_id}/run").status_code == 200
    assert client.post(f"{BASE}/{research_id}/run").status_code == 200
    assert uuid.UUID(research_id) not in run_module._running


def test_status_is_available_while_run_is_in_flight(env) -> None:
    """Regression: status used to 404 until the whole pipeline finished."""
    client, _, _ = env
    research_id = _create_research(client)
    observed: dict = {}

    class _Search:
        def search(self, query):
            orch = run_module._orchestrators_by_research[uuid.UUID(research_id)]
            state = asyncio.run(orch.get_state_by_research(uuid.UUID(research_id)))
            observed["stage"] = state.current_stage.value
            return []

    class _Planner:
        async def plan(self, plan_input):
            from app.services.planning.schemas import (
                PlanTask, ResearchPlan, TaskStatus, TaskType,
            )

            task = PlanTask(
                task_id=uuid.uuid4(), title="q", description="d", priority=1,
                task_type=TaskType.SEARCH, status=TaskStatus.PENDING,
            )
            return ResearchPlan(
                plan_id=uuid.uuid4(), research_id=plan_input.research_id,
                tasks=[task], created_at=datetime.now(UTC),
            )

    class _R:
        objective, question = "o", "q"

    _use_nodes(lambda: ResearchNodes(
        planner=_Planner(), research_loader=lambda rid: _R(), search=_Search()
    ))

    assert client.post(f"{BASE}/{research_id}/run").status_code == 200
    assert observed["stage"] == WorkflowStage.SEARCHING.value


def test_run_accepts_optional_focus_and_rejects_unknown_fields(env) -> None:
    client, _, _ = env
    research_id = _create_research(client)
    _use_nodes(ResearchNodes)

    with_focus = client.post(f"{BASE}/{research_id}/run", json={"focus": "impacto ambiental"})
    bad_body = client.post(f"{BASE}/{research_id}/run", json={"nope": 1})

    assert with_focus.status_code == 200
    assert with_focus.json()["research_focus"] == "impacto ambiental"
    assert bad_body.status_code == 422


def test_run_accepts_empty_body_with_json_content_type(env) -> None:
    """The browser sends POST with Content-Type: application/json and no body."""
    client, _, _ = env
    research_id = _create_research(client)
    _use_nodes(ResearchNodes)

    resp = client.post(f"{BASE}/{research_id}/run", headers={"Content-Type": "application/json"})

    assert resp.status_code == 200
    assert resp.json()["research_focus"] is None
