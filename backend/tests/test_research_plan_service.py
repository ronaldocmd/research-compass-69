"""Tests for ResearchPlanService (RDA-031)."""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.plan import PlanStatus
from app.models.research import Research, ResearchStatus
from app.repositories.research_plan_repository import ResearchPlanRepository
from app.repositories.research_repository import ResearchRepository
from app.services.llm.exceptions import InvalidLLMResponseError
from app.services.llm.provider import LLMProvider
from app.services.planning.exceptions import InvalidPlanError
from app.services.planning.planner import ResearchPlanner
from app.services.planning.schemas import PlanTaskDraft
from app.services.research_plan_service import ResearchPlanNotFoundError, ResearchPlanService
from app.services.research_service import ResearchNotFoundError


class _FakeLLMProvider(LLMProvider):
    name = "fake"

    def __init__(self, *, tasks=None, error=None) -> None:
        self.model = "fake-model"
        self._tasks = tasks
        self._error = error

    def complete(self, prompt, response_model):
        if self._error is not None:
            raise self._error
        return response_model(tasks=self._tasks or [])


def _draft(title: str, priority: int = 1, task_type: str = "SEARCH") -> PlanTaskDraft:
    return PlanTaskDraft(
        title=title, description=f"{title} description", priority=priority, task_type=task_type
    )


def _planner(tasks=None, error=None) -> ResearchPlanner:
    return ResearchPlanner(llm=_FakeLLMProvider(tasks=tasks, error=error))


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


@pytest.fixture
def research(db: Session) -> Research:
    return ResearchRepository(db).create(
        title="T", objective="o", question="q", status=ResearchStatus.DRAFT
    )


def test_create_plan_saves_plan_and_tasks(db: Session, research: Research) -> None:
    planner = _planner(tasks=[_draft("A", 1), _draft("B", 2), _draft("C", 3)])
    service = ResearchPlanService(db, planner=planner)

    record = service.create_plan(research.id, sources=["openalex"])

    assert record.status == PlanStatus.CREATED
    tasks = service.list_tasks(research.id)
    assert [t.title for t in tasks] == ["A", "B", "C"]


def test_list_tasks_ordered_by_priority(db: Session, research: Research) -> None:
    planner = _planner(tasks=[_draft("low", 3), _draft("high", 1), _draft("mid", 2)])
    service = ResearchPlanService(db, planner=planner)
    service.create_plan(research.id)

    tasks = service.list_tasks(research.id)

    assert [t.title for t in tasks] == ["high", "mid", "low"]


def test_create_plan_replaces_previous(db: Session, research: Research) -> None:
    ResearchPlanService(db, planner=_planner(tasks=[_draft("first", 1), _draft("x", 2), _draft("y", 3)])).create_plan(research.id)
    ResearchPlanService(db, planner=_planner(tasks=[_draft("second", 1), _draft("z", 2), _draft("w", 3)])).create_plan(research.id)

    tasks = ResearchPlanService(db, planner=_planner()).list_tasks(research.id)

    assert [t.title for t in tasks] == ["second", "z", "w"]
    plans = ResearchPlanRepository(db).list_by_research_id(research.id)
    assert len(plans) == 1


def test_invalid_llm_does_not_save(db: Session, research: Research) -> None:
    service = ResearchPlanService(db, planner=_planner(error=InvalidLLMResponseError("bad")))

    with pytest.raises(InvalidPlanError):
        service.create_plan(research.id)

    with pytest.raises(ResearchPlanNotFoundError):
        service.get_plan(research.id)


def test_create_plan_unknown_research_raises(db: Session) -> None:
    service = ResearchPlanService(db, planner=_planner(tasks=[_draft("a"), _draft("b"), _draft("c")]))

    with pytest.raises(ResearchNotFoundError):
        service.create_plan(uuid.uuid4())
