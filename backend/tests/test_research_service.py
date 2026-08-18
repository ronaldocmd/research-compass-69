"""Unit tests for ResearchService (RDA-006).

No database is used: the repository is mocked so the service's business rules
are tested in isolation.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from app.models.research import Research, ResearchStatus
from app.repositories.research_repository import ResearchRepository
from app.schemas.research import ResearchCreate, ResearchUpdate
from app.services.research_service import ResearchNotFoundError, ResearchService


@pytest.fixture
def repository() -> MagicMock:
    return MagicMock(spec=ResearchRepository)


@pytest.fixture
def service(repository: MagicMock) -> ResearchService:
    service = ResearchService.__new__(ResearchService)
    service.repository = repository
    return service


def test_create_returns_persisted_research(service: ResearchService, repository: MagicMock) -> None:
    payload = ResearchCreate(
        title="Novo título",
        objective="Objetivo",
        question="Pergunta",
        status=ResearchStatus.DRAFT,
    )
    expected = Research(
        id=uuid.uuid4(),
        title=payload.title,
        objective=payload.objective,
        question=payload.question,
        status=payload.status,
    )
    repository.create.return_value = expected

    result = service.create(payload)

    repository.create.assert_called_once_with(
        title=payload.title,
        objective=payload.objective,
        question=payload.question,
        status=payload.status,
    )
    assert result == expected


def test_list_delegates_to_repository(service: ResearchService, repository: MagicMock) -> None:
    expected = [
        Research(id=uuid.uuid4(), title="A", objective="obj", question="q", status=ResearchStatus.DRAFT)
    ]
    repository.list.return_value = expected

    result = service.list(limit=10, offset=5)

    repository.list.assert_called_once_with(limit=10, offset=5)
    assert result == expected


def test_get_returns_research_when_found(service: ResearchService, repository: MagicMock) -> None:
    research_id = uuid.uuid4()
    expected = Research(
        id=research_id,
        title="T",
        objective="o",
        question="q",
        status=ResearchStatus.READY,
    )
    repository.get.return_value = expected

    result = service.get(research_id)

    repository.get.assert_called_once_with(research_id)
    assert result == expected


def test_get_raises_research_not_found_when_missing(service: ResearchService, repository: MagicMock) -> None:
    research_id = uuid.uuid4()
    repository.get.return_value = None

    with pytest.raises(ResearchNotFoundError) as exc_info:
        service.get(research_id)

    assert exc_info.value.research_id == research_id


def test_update_returns_updated_research(service: ResearchService, repository: MagicMock) -> None:
    research_id = uuid.uuid4()
    existing = Research(
        id=research_id,
        title="Antigo",
        objective="obj",
        question="q",
        status=ResearchStatus.DRAFT,
    )
    repository.get.return_value = existing
    updated = Research(
        id=research_id,
        title="Novo",
        objective="obj",
        question="q",
        status=ResearchStatus.READY,
    )
    repository.update.return_value = updated

    payload = ResearchUpdate(title="Novo", status=ResearchStatus.READY)
    result = service.update(research_id, payload)

    repository.get.assert_called_once_with(research_id)
    repository.update.assert_called_once_with(existing, title="Novo", status=ResearchStatus.READY)
    assert result == updated


def test_update_returns_existing_when_no_changes(service: ResearchService, repository: MagicMock) -> None:
    research_id = uuid.uuid4()
    existing = Research(
        id=research_id,
        title="T",
        objective="o",
        question="q",
        status=ResearchStatus.DRAFT,
    )
    repository.get.return_value = existing

    result = service.update(research_id, ResearchUpdate())

    repository.update.assert_not_called()
    assert result == existing


def test_delete_delegates_to_repository(service: ResearchService, repository: MagicMock) -> None:
    research_id = uuid.uuid4()
    existing = Research(
        id=research_id,
        title="T",
        objective="o",
        question="q",
        status=ResearchStatus.DRAFT,
    )
    repository.get.return_value = existing

    service.delete(research_id)

    repository.get.assert_called_once_with(research_id)
    repository.delete.assert_called_once_with(existing)


def test_delete_raises_research_not_found_when_missing(service: ResearchService, repository: MagicMock) -> None:
    research_id = uuid.uuid4()
    repository.get.return_value = None

    with pytest.raises(ResearchNotFoundError):
        service.delete(research_id)

    repository.delete.assert_not_called()
