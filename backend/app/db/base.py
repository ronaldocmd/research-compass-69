from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models (Alembic autogenerate target)."""


# Import models here so Alembic can discover them.
from app.models import *  # noqa: E402,F401,F403
