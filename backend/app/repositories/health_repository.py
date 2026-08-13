import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class HealthRepository:
    """Only layer allowed to touch the database."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def ping(self) -> bool:
        try:
            self.db.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError as exc:  # pragma: no cover - depends on infra
            logger.warning("Database ping failed: %s", exc)
            return False
