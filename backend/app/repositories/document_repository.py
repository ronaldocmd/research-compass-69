"""Data access for the `documents` table (RDA-017).

Only this layer touches the database; the Service layer depends on it.
Mirrors the shape of ResearchRepository (RDA-006).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document


class DocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, **values: object) -> Document:
        document = Document(**values)
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def bulk_create(self, documents_data: list[dict]) -> list[Document]:
        documents = [Document(**values) for values in documents_data]
        self.db.add_all(documents)
        self.db.commit()
        for document in documents:
            self.db.refresh(document)
        return documents

    def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        return self.db.get(Document, document_id)

    def get_by_research_id(
        self, research_id: uuid.UUID, *, skip: int = 0, limit: int = 50
    ) -> list[Document]:
        stmt = (
            select(Document)
            .where(Document.research_id == research_id)
            .order_by(Document.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())

    def update(self, document: Document, **values: object) -> Document:
        for field, value in values.items():
            setattr(document, field, value)
        self.db.commit()
        self.db.refresh(document)
        return document

    def delete(self, document: Document) -> bool:
        self.db.delete(document)
        self.db.commit()
        return True
