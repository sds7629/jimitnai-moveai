from __future__ import annotations

from datetime import datetime, timezone

from app.models.document import Document, DocumentChunk
from app.repositories.base import MutableRepository


class DocumentRepository(MutableRepository[Document]):
    """Mutable: a document's valid_until may need to be closed out when a
    newer version supersedes it."""

    model = Document

    def by_type(self, doc_type: str) -> list[Document]:
        return self.db.query(Document).filter(Document.doc_type == doc_type).all()


class DocumentChunkRepository(MutableRepository[DocumentChunk]):
    model = DocumentChunk

    def search(
        self,
        doc_types: list[str] | None = None,
        top_k: int = 5,
        as_of: datetime | None = None,
    ) -> list[DocumentChunk]:
        """Minimal doc_type + validity-window filtered lookup. Real
        pgvector cosine-similarity ranking (`embedding <=> query_vector`)
        is knowledge-retrieval's responsibility (agents/knowledge-retrieval.md)
        — this stub only guarantees the filter contract (doc_type list +
        expired contract/SOP exclusion) that persona builds on top of.
        """
        as_of = as_of or datetime.now(timezone.utc)
        query = (
            self.db.query(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
        )
        if doc_types:
            query = query.filter(Document.doc_type.in_(doc_types))
        query = query.filter(
            (Document.valid_until.is_(None)) | (Document.valid_until >= as_of)
        )
        return query.order_by(DocumentChunk.id.asc()).limit(top_k).all()
