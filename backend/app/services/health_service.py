from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.health_repository import HealthRepository
from app.schemas.health import HealthResponse


class HealthService:
    """Business layer: never talks to the database directly."""

    def __init__(self, db: Session) -> None:
        self.repository = HealthRepository(db)

    def check(self) -> HealthResponse:
        database = "up" if self.repository.ping() else "down"
        return HealthResponse(status="ok", database=database, version=settings.VERSION)
