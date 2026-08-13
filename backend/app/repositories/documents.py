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
        *,
        query_embedding: list[float] | None = None,
    ) -> list[DocumentChunk]:
        """doc_type 필터 + 유효기간 필터 + (query_embedding이 주어지면) pgvector
        코사인 유사도 정렬을 적용한 청크 검색.

        agents/knowledge-retrieval.md 원칙: 유사도만으로 정렬해 만료된 계약/
        SOP 조항이 근거로 쓰이는 것을 막기 위해, 유사도 정렬 이전에 doc_type
        필터와 유효기간 필터(`valid_until IS NULL OR valid_until >= as_of`)를
        먼저 적용한다.

        `query_embedding`을 넘기지 않으면(과거 스텁과 동일하게) id 순으로
        반환한다 — 이 경우도 doc_type/유효기간 필터 계약은 그대로 보장된다.
        상위 진입점은 `app.rag.search.search_similar_chunks`를 참고.
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
        if query_embedding is not None:
            query = query.order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        else:
            query = query.order_by(DocumentChunk.id.asc())
        return query.limit(top_k).all()
