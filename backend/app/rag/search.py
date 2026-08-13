"""지식 검색 에이전트의 공개 검색 진입점 (agents/knowledge-retrieval.md).

시뮬레이션 에이전트 등 다음 웨이브는 `search_similar_chunks` 하나만 호출하면
된다:

    from app.rag.search import search_similar_chunks

    results = search_similar_chunks(
        db,
        "부산항 하역 지연으로 부품 재고가 소진되는 상황",
        doc_types=["사고", "플레이북"],
        top_k=5,
    )

내부적으로는:
  1. `query_text`를 Gemini Embedding API(`app.llm.gemini_embeddings.embed_text`)로
     768차원 벡터로 변환하고,
  2. `DocumentChunkRepository.search()`가 pgvector 코사인 유사도 정렬 +
     `doc_type` 필터 + 유효기간 필터(계약/SOP의 만료본 제외)를 적용해 top-k
     청크를 가져온 뒤,
  3. LLM 프롬프트에 바로 삽입할 수 있는 평범한 dict 목록으로 펼쳐 반환한다.

실제 GEMINI_API_KEY 없이 호출부를 테스트하려면 `embed_fn`에 fake 함수를
주입하면 된다 (`app/llm/gemini_api.py` 테스트와 동일한 패턴).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app.llm.gemini_embeddings import embed_text
from app.models.document import Document
from app.repositories.documents import DocumentChunkRepository

EmbedFn = Callable[[str], list[float]]


def search_similar_chunks(
    db: Session,
    query_text: str,
    doc_types: list[str] | None = None,
    top_k: int = 5,
    as_of: datetime | None = None,
    embed_fn: EmbedFn | None = None,
) -> list[dict]:
    """쿼리 텍스트를 임베딩한 뒤 유사 청크를 검색해 dict 목록으로 반환한다.

    반환값의 각 원소는 다음 키를 갖는다:
      - chunk_id (int)
      - document_id (int)
      - doc_type (str | None)   -- '사고' | 'SOP' | '계약' | '플레이북'
      - title (str | None)
      - source (str | None)
      - chunk_type (str)        -- '사건' | '절차' | '조항' | '대응패턴'
      - chunk_text (str)
      - metadata (dict)

    존재하지 않는 doc_type만 필터로 넘기거나, 조건에 맞는 청크가 하나도
    없으면 빈 리스트를 반환한다 (예외를 던지지 않는다).
    """
    embed = embed_fn or embed_text
    query_embedding = embed(query_text)

    repo = DocumentChunkRepository(db)
    chunks = repo.search(doc_types, top_k, as_of, query_embedding=query_embedding)
    if not chunks:
        return []

    document_ids = {chunk.document_id for chunk in chunks}
    documents_by_id = {
        document.id: document
        for document in db.query(Document).filter(Document.id.in_(document_ids)).all()
    }

    results: list[dict] = []
    for chunk in chunks:
        document = documents_by_id.get(chunk.document_id)
        results.append(
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "doc_type": document.doc_type if document else None,
                "title": document.title if document else None,
                "source": document.source if document else None,
                "chunk_type": chunk.chunk_type,
                "chunk_text": chunk.chunk_text,
                "metadata": chunk.metadata_,
            }
        )
    return results
