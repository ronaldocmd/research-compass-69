"""Unit tests for EvaluationRepository (RDA-049).

Uses an in-memory SQLite database to exercise the real SQLAlchemy queries
without requiring PostgreSQL.
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.human_evaluation import HumanEvaluation
from app.repositories.evaluation_repository import EvaluationRepository
from app.schemas.evaluation import HumanEvaluationCreate


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables["human_evaluations"]]
    )
    factory: sessionmaker[Session] = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def _payload(
    claim_id: uuid.UUID | None = None,
    research_id: uuid.UUID | None = None,
    rating: str = "correct",
    evaluator_id: str = "evaluator@example.com",
    comment: str | None = None,
) -> HumanEvaluationCreate:
    return HumanEvaluationCreate(
        claim_id=claim_id or uuid.uuid4(),
        research_id=research_id or uuid.uuid4(),
        evaluator_id=evaluator_id,
        rating=rating,  # type: ignore[arg-type]
        comment=comment,
    )


def test_create_evaluation_persists_and_returns(db: Session) -> None:
    repo = EvaluationRepository(db)
    payload = _payload(comment="Bem fundamentado")

    result = repo.create_evaluation(payload)

    assert isinstance(result.id, uuid.UUID)
    assert result.claim_id == payload.claim_id
    assert result.research_id == payload.research_id
    assert result.evaluator_id == payload.evaluator_id
    assert result.rating == "correct"
    assert result.comment == "Bem fundamentado"
    assert result.evaluated_at is not None

    fetched = db.get(HumanEvaluation, result.id)
    assert fetched is not None
    assert fetched.rating == "correct"


def test_get_by_claim_returns_only_that_claim(db: Session) -> None:
    repo = EvaluationRepository(db)
    claim_a = uuid.uuid4()
    claim_b = uuid.uuid4()
    repo.create_evaluation(_payload(claim_id=claim_a))
    repo.create_evaluation(_payload(claim_id=claim_a, rating="incorrect"))
    repo.create_evaluation(_payload(claim_id=claim_b))

    results = repo.get_by_claim(claim_a)

    assert len(results) == 2
    assert all(item.claim_id == claim_a for item in results)


def test_get_by_research_returns_only_that_research(db: Session) -> None:
    repo = EvaluationRepository(db)
    research_a = uuid.uuid4()
    research_b = uuid.uuid4()
    repo.create_evaluation(_payload(research_id=research_a))
    repo.create_evaluation(_payload(research_id=research_a, rating="inconclusive"))
    repo.create_evaluation(_payload(research_id=research_b))

    results = repo.get_by_research(research_a)

    assert len(results) == 2
    assert all(item.research_id == research_a for item in results)


def test_get_statistics_distribution(db: Session) -> None:
    repo = EvaluationRepository(db)
    research_id = uuid.uuid4()
    repo.create_evaluation(_payload(research_id=research_id, rating="correct"))
    repo.create_evaluation(_payload(research_id=research_id, rating="correct"))
    repo.create_evaluation(_payload(research_id=research_id, rating="incorrect"))
    repo.create_evaluation(_payload(research_id=research_id, rating="inconclusive"))

    stats = repo.get_statistics(research_id)

    assert stats["total"] == 4
    assert stats["correct"] == 0.5
    assert stats["incorrect"] == 0.25
    assert stats["inconclusive"] == 0.25


def test_get_statistics_empty_research(db: Session) -> None:
    repo = EvaluationRepository(db)

    stats = repo.get_statistics(uuid.uuid4())

    assert stats == {"total": 0, "correct": 0.0, "incorrect": 0.0, "inconclusive": 0.0}


def test_multiple_evaluations_per_claim_are_kept(db: Session) -> None:
    repo = EvaluationRepository(db)
    claim_id = uuid.uuid4()
    research_id = uuid.uuid4()
    first = repo.create_evaluation(
        _payload(claim_id=claim_id, research_id=research_id, rating="correct")
    )
    second = repo.create_evaluation(
        _payload(
            claim_id=claim_id,
            research_id=research_id,
            rating="incorrect",
            evaluator_id="second@example.com",
        )
    )

    results = repo.get_by_claim(claim_id)

    assert len(results) == 2
    assert {item.id for item in results} == {first.id, second.id}
    assert {item.rating for item in results} == {"correct", "incorrect"}
