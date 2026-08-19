"""Tests for ResearchPlanRepository and PlanTaskRepository (RDA-031)."""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.plan import PlanStatus, PlanTaskRecord, ResearchPlanRecord, TaskStatus, TaskType
from app.models.research import Research, ResearchStatus
from app.repositories.plan_task_repository import PlanTaskRepository
from app.repositories.research_plan_repository import ResearchPlanRepository
from app.repositories.research_repository import ResearchRepository


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


def test_create_plan_persists(db: Session, research: Research) -> None:
    plan = ResearchPlanRepository(db).create(
        research_id=research.id, status=PlanStatus.CREATED
    )

    assert isinstance(plan.id, uuid.UUID)
    assert plan.research_id == research.id
    assert plan.status == PlanStatus.CREATED
    assert db.get(ResearchPlanRecord, plan.id) is not None


def test_get_by_research_id_returns_plan(db: Session, research: Research) -> None:
    repo = ResearchPlanRepository(db)
    created = repo.create(research_id=research.id, status=PlanStatus.CREATED)

    result = repo.get_by_research_id(research.id)

    assert result is not None
    assert result.id == created.id


def test_get_by_research_id_returns_none_when_missing(
    db: Session, research: Research
) -> None:
    assert ResearchPlanRepository(db).get_by_research_id(research.id) is None


def test_delete_by_research_id_removes_plan_and_tasks(
    db: Session, research: Research
) -> None:
    plan_repo = ResearchPlanRepository(db)
    task_repo = PlanTaskRepository(db)
    plan = plan_repo.create(research_id=research.id, status=PlanStatus.CREATED)
    task = task_repo.create(
        plan_id=plan.id,
        title="t",
        description="d",
        priority=1,
        task_type=TaskType.SEARCH,
        status=TaskStatus.PENDING,
        order=0,
    )

    plan_repo.delete_by_research_id(research.id)

    assert db.get(ResearchPlanRecord, plan.id) is None
    assert db.get(PlanTaskRecord, task.id) is None


def test_tasks_listed_ordered_by_priority(db: Session, research: Research) -> None:
    plan = ResearchPlanRepository(db).create(
        research_id=research.id, status=PlanStatus.CREATED
    )
    PlanTaskRepository(db).bulk_create(
        [
            dict(plan_id=plan.id, title="low", description="d", priority=3,
                 task_type=TaskType.SEARCH, status=TaskStatus.PENDING, order=0),
            dict(plan_id=plan.id, title="high", description="d", priority=1,
                 task_type=TaskType.SEARCH, status=TaskStatus.PENDING, order=1),
            dict(plan_id=plan.id, title="mid", description="d", priority=2,
                 task_type=TaskType.SEARCH, status=TaskStatus.PENDING, order=2),
        ]
    )

    tasks = PlanTaskRepository(db).list_by_plan_id(plan.id)

    assert [t.title for t in tasks] == ["high", "mid", "low"]
