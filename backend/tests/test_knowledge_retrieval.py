"""Tests for the knowledge-retrieval RAG pipeline (agents/knowledge-retrieval.md).

Covers the DoD's minimum 3 cases plus edge cases across chunking, embeddings,
and the pgvector-backed search entry point:

  1. Normal search returns ranked results (closest embedding first) merged
     with doc_type/title/chunk_type metadata.
  2. Expired contract chunks are excluded by the validity-window filter.
  3. Querying an unknown doc_type returns an empty result, not an error.

Plus: 4 separate chunking strategies (not one generic chunker), the
backward-compatible repository search() contract, Gemini embedding error
handling, and the seed script's idempotent per-doc-type loading.

These hit the real app + real Postgres (docker compose's `db` service),
matching test_incident_intake.py / test_append_only.py style. Gemini calls
are always faked/mocked here -- no network, no API key required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.llm.gemini_api import GeminiAPIError
from app.llm.gemini_embeddings import EMBEDDING_DIM, embed_text
from app.rag.chunking import chunk_contract, chunk_incident, chunk_playbook, chunk_sop
from app.rag.search import search_similar_chunks
from app.repositories.documents import DocumentChunkRepository, DocumentRepository

# A per-run random offset keeps this run's fake embeddings from tying with
# leftover chunks inserted by earlier runs against the same persistent dev DB
# (documents/document_chunks have no delete() -- same convention as
# test_incident_intake.py's _RUN_ID).
_RUN_ID = uuid.uuid4().hex[:8]
_RUN_OFFSET = int(_RUN_ID, 16) % (EMBEDDING_DIM - 10)


def _one_hot(index: int) -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    vec[index % EMBEDDING_DIM] = 1.0
    return vec


def _title(base: str) -> str:
    return f"{base} ({_RUN_ID})"


@pytest.fixture()
def doc_repo(db_session):
    return DocumentRepository(db_session)


@pytest.fixture()
def chunk_repo(db_session):
    return DocumentChunkRepository(db_session)


def _make_document(repo, *, doc_type, title, valid_from=None, valid_until=None):
    return repo.add(
        doc_type=doc_type,
        title=title,
        source="test-fixture",
        valid_from=valid_from,
        valid_until=valid_until,
    )


def _make_chunk(repo, document, *, chunk_text, chunk_type, embedding, metadata=None):
    return repo.add(
        document_id=document.id,
        chunk_text=chunk_text,
        chunk_type=chunk_type,
        embedding=embedding,
        metadata_=metadata or {},
    )


# ============================================================
# DoD case 1: normal search returns ranked results
# ============================================================
def test_search_similar_chunks_ranks_closest_embedding_first(db_session, doc_repo, chunk_repo):
    near_idx = _RUN_OFFSET
    far_idx = _RUN_OFFSET + 1

    doc = _make_document(doc_repo, doc_type="사고", title=_title("적체 사고 리포트"))
    near_chunk = _make_chunk(
        chunk_repo, doc,
        chunk_text="항만 적체로 인한 재고 소진 사건",
        chunk_type="사건",
        embedding=_one_hot(near_idx),
    )
    _make_chunk(
        chunk_repo, doc,
        chunk_text="전혀 관련 없는 사건",
        chunk_type="사건",
        embedding=_one_hot(far_idx),
    )

    results = search_similar_chunks(
        db_session,
        "항만 적체 관련 과거 사고를 찾아줘",
        doc_types=["사고"],
        top_k=1,
        embed_fn=lambda _text: _one_hot(near_idx),
    )

    assert len(results) == 1
    assert results[0]["chunk_id"] == near_chunk.id
    assert results[0]["doc_type"] == "사고"
    assert results[0]["chunk_type"] == "사건"
    assert results[0]["chunk_text"] == "항만 적체로 인한 재고 소진 사건"


# ============================================================
# DoD case 2: expired contract chunks are excluded
# ============================================================
def test_search_excludes_expired_contract(db_session, doc_repo, chunk_repo):
    idx = _RUN_OFFSET + 2
    now = datetime.now(timezone.utc)

    expired_doc = _make_document(
        doc_repo, doc_type="계약", title=_title("해상운송 계약서 구버전"),
        valid_from=now - timedelta(days=365 * 3),
        valid_until=now - timedelta(days=30),
    )
    current_doc = _make_document(
        doc_repo, doc_type="계약", title=_title("해상운송 계약서 현행"),
        valid_from=now - timedelta(days=365),
        valid_until=None,
    )
    _make_chunk(
        chunk_repo, expired_doc,
        chunk_text="지연배상 0.5% (구버전, 만료됨)",
        chunk_type="조항",
        embedding=_one_hot(idx),
    )
    current_chunk = _make_chunk(
        chunk_repo, current_doc,
        chunk_text="지연배상 0.8% (현행)",
        chunk_type="조항",
        embedding=_one_hot(idx),
    )

    results = search_similar_chunks(
        db_session,
        "지연배상 조항이 뭐였지",
        doc_types=["계약"],
        top_k=10,
        as_of=now,
        embed_fn=lambda _text: _one_hot(idx),
    )

    result_ids = {r["chunk_id"] for r in results}
    assert current_chunk.id in result_ids
    assert all(r["chunk_text"] != "지연배상 0.5% (구버전, 만료됨)" for r in results)


# ============================================================
# DoD case 3: unknown doc_type returns empty result
# ============================================================
def test_search_unknown_doc_type_returns_empty_list(db_session):
    results = search_similar_chunks(
        db_session,
        "아무 쿼리",
        doc_types=["존재하지않는유형"],
        top_k=5,
        embed_fn=lambda _text: _one_hot(0),
    )
    assert results == []


# ============================================================
# Repository-level contract stays backward compatible: positional
# doc_types/top_k/as_of still work without query_embedding, and still
# apply the doc_type filter.
# ============================================================
def test_repository_search_positional_args_without_embedding_still_filters(
    db_session, doc_repo, chunk_repo
):
    doc = _make_document(doc_repo, doc_type="SOP", title=_title("SOP 문서"))
    inserted = _make_chunk(
        chunk_repo, doc, chunk_text="1단계 내용", chunk_type="절차",
        embedding=_one_hot(_RUN_OFFSET + 3),
    )

    repo = DocumentChunkRepository(db_session)
    results = repo.search(["SOP"], 50)  # positional call, no query_embedding kwarg

    assert inserted.id in {c.id for c in results}


def test_repository_search_unknown_doc_type_positional_returns_empty(db_session):
    repo = DocumentChunkRepository(db_session)
    assert repo.search(["존재하지않는유형"], 5) == []


# ============================================================
# Chunking: 4 separate strategies, not a single generic chunker.
# ============================================================
def test_chunk_contract_splits_by_clause_article():
    text = (
        "제1조(목적) 이것은 목적 조항이다.\n"
        "제2조(지연배상) 지연 시 배상금을 지급한다.\n"
    )
    chunks = chunk_contract(text)
    assert len(chunks) == 2
    assert all(c.chunk_type == "조항" for c in chunks)
    assert chunks[0].metadata["clause_no"] == "제1조"
    assert chunks[1].metadata["clause_no"] == "제2조"


def test_chunk_sop_splits_by_procedure_step():
    text = "1단계: 감지\n사건을 감지한다.\n2단계: 분류\n유형을 분류한다.\n"
    chunks = chunk_sop(text)
    assert len(chunks) == 2
    assert all(c.chunk_type == "절차" for c in chunks)
    assert chunks[0].metadata["step_no"] == 1
    assert chunks[1].metadata["step_no"] == 2


def test_chunk_incident_combines_cause_response_result_into_one_chunk():
    text = (
        "사건 1: 태풍 하역 중단\n"
        "원인: 태풍 영향으로 하역이 중단되었다.\n"
        "대응: 대체항으로 우회했다.\n"
        "결과: 정상화되었다.\n"
    )
    chunks = chunk_incident(text)
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "사건"
    # 원인/대응/결과가 분리된 청크가 아니라 하나의 청크 안에 모두 들어있어야 한다.
    assert "원인" in chunks[0].chunk_text
    assert "대응" in chunks[0].chunk_text
    assert "결과" in chunks[0].chunk_text
    assert chunks[0].metadata["cause"].startswith("태풍")
    assert chunks[0].metadata["response"].startswith("대체항")
    assert chunks[0].metadata["result"].startswith("정상화")


def test_chunk_playbook_splits_by_response_pattern():
    text = "패턴 1: 대체항 우회\n조치 내용 1.\n패턴 2: 긴급운송\n조치 내용 2.\n"
    chunks = chunk_playbook(text)
    assert len(chunks) == 2
    assert all(c.chunk_type == "대응패턴" for c in chunks)
    assert chunks[0].metadata["pattern_id"] == "1"
    assert chunks[1].metadata["pattern_id"] == "2"


def test_chunkers_produce_distinct_chunk_types_per_doc_type():
    # 서로 다른 문서 유형은 서로 다른 chunk_type을 갖는다 -- 범용 청커 하나로
    # 통일하지 않았다는 것을 chunk_type 다양성으로 확인한다.
    contract_types = {c.chunk_type for c in chunk_contract("제1조(목적) 목적이다.")}
    sop_types = {c.chunk_type for c in chunk_sop("1단계: 시작\n내용.")}
    incident_types = {
        c.chunk_type for c in chunk_incident("사건 1: 제목\n원인: a\n대응: b\n결과: c\n")
    }
    playbook_types = {c.chunk_type for c in chunk_playbook("패턴 1: 이름\n내용.")}

    assert contract_types | sop_types | incident_types | playbook_types == {
        "조항", "절차", "사건", "대응패턴",
    }


# ============================================================
# Gemini Embedding API wrapper
# ============================================================
def test_embed_text_raises_without_api_key_or_client(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", None)
    with pytest.raises(GeminiAPIError):
        embed_text("hello")


def test_embed_text_returns_768_dim_vector_with_fake_client():
    fake_embedding = MagicMock(values=[0.1] * EMBEDDING_DIM)
    fake_response = MagicMock(embeddings=[fake_embedding])
    client = MagicMock()
    client.models.embed_content.return_value = fake_response

    result = embed_text("hello", client=client)

    assert len(result) == EMBEDDING_DIM
    client.models.embed_content.assert_called_once()


def test_embed_text_wrong_dimension_raises_gemini_api_error():
    fake_embedding = MagicMock(values=[0.1] * 10)  # wrong size
    fake_response = MagicMock(embeddings=[fake_embedding])
    client = MagicMock()
    client.models.embed_content.return_value = fake_response

    with pytest.raises(GeminiAPIError):
        embed_text("hello", client=client)


def test_embed_text_wraps_client_exception_as_gemini_api_error():
    client = MagicMock()
    client.models.embed_content.side_effect = RuntimeError("network down")

    with pytest.raises(GeminiAPIError, match="network down"):
        embed_text("hello", client=client)


# ------------------------------------------------------------------
# GEMINI_USE_VERTEX_AI wiring -- added after discovering (via a real key)
# that this project's actual GEMINI_API_KEY is a Vertex AI Express Mode key,
# which 403s with API_KEY_SERVICE_BLOCKED unless vertexai=True is passed to
# genai.Client(). embed_text() only builds its own client (and so only
# consults this flag) when no `client=` is injected, so these two tests
# monkeypatch `_build_client` itself to capture what it was called with,
# instead of injecting a fake client (which would bypass this wiring
# entirely, like every other test above).
# ------------------------------------------------------------------
def _fake_embed_content_client(*, api_key=None, use_vertex_ai=True):
    client = MagicMock()
    client.models.embed_content.return_value = MagicMock(embeddings=[MagicMock(values=[0.0] * EMBEDDING_DIM)])
    return client


def test_embed_text_defaults_to_settings_use_vertex_ai(monkeypatch):
    from app.core.config import settings

    captured = {}

    def _capturing_build_client(api_key, use_vertex_ai=True):
        captured["use_vertex_ai"] = use_vertex_ai
        return _fake_embed_content_client()

    monkeypatch.setattr(settings, "gemini_api_key", "fake-key")
    monkeypatch.setattr(settings, "gemini_use_vertex_ai", True)
    monkeypatch.setattr("app.llm.gemini_embeddings._build_client", _capturing_build_client)

    embed_text("hello")

    assert captured["use_vertex_ai"] is True


def test_embed_text_explicit_use_vertex_ai_overrides_settings(monkeypatch):
    from app.core.config import settings

    captured = {}

    def _capturing_build_client(api_key, use_vertex_ai=True):
        captured["use_vertex_ai"] = use_vertex_ai
        return _fake_embed_content_client()

    monkeypatch.setattr(settings, "gemini_api_key", "fake-key")
    monkeypatch.setattr(settings, "gemini_use_vertex_ai", True)  # settings say True...
    monkeypatch.setattr("app.llm.gemini_embeddings._build_client", _capturing_build_client)

    embed_text("hello", use_vertex_ai=False)  # ...but the explicit call param wins

    assert captured["use_vertex_ai"] is False


# ============================================================
# Seed script: doc-type-specific chunking actually lands in the DB, and
# reruns are idempotent (no duplicate documents).
# ============================================================
def test_seed_script_creates_documents_with_distinct_chunk_types(db_session, monkeypatch):
    from app.scripts import seed_documents

    # Isolate this test run from any previous run's seeded titles so
    # run_seed's idempotency check doesn't just skip everything.
    suffixed = [
        seed_documents.SeedDocument(
            doc_type=d.doc_type,
            title=_title(d.title),
            source=d.source,
            raw_text=d.raw_text,
            valid_from=d.valid_from,
            valid_until=d.valid_until,
        )
        for d in seed_documents.SEED_DOCUMENTS
    ]
    monkeypatch.setattr(seed_documents, "SEED_DOCUMENTS", suffixed)

    fake_embed = lambda _text: _one_hot(_RUN_OFFSET + 4)  # noqa: E731

    summary = seed_documents.run_seed(db_session, embed_fn=fake_embed)

    assert summary["documents_created"] == len(suffixed)
    assert summary["chunks_created"] > 0

    created_doc_types = {d.doc_type for d in suffixed}
    assert created_doc_types == {"사고", "SOP", "플레이북", "계약"}

    # Re-running is idempotent: second call skips every title (already exists).
    summary_again = seed_documents.run_seed(db_session, embed_fn=fake_embed)
    assert summary_again["documents_created"] == 0
    assert summary_again["documents_skipped"] == len(suffixed)


def test_seed_script_does_not_leave_orphan_document_on_embedding_failure(db_session, monkeypatch):
    """A document must be all-or-nothing: if embedding fails partway through
    a document's chunks (e.g. GEMINI_API_KEY missing/revoked mid-run), no
    Document row with zero chunks should be left behind -- otherwise a
    later retry's title-based idempotency check would treat it as already
    fully seeded and skip it forever (see run_seed's comment)."""
    from app.models.document import Document
    from app.scripts import seed_documents

    failing_title = _title("실패해야 하는 사고 문서")
    one_seed_doc = seed_documents.SeedDocument(
        doc_type="사고",
        title=failing_title,
        source="test-fixture",
        raw_text="사건 1: 제목\n원인: a\n대응: b\n결과: c\n",
    )
    monkeypatch.setattr(seed_documents, "SEED_DOCUMENTS", [one_seed_doc])

    def always_fails(_text):
        raise GeminiAPIError("GEMINI_API_KEY가 설정되지 않았습니다.")

    with pytest.raises(GeminiAPIError):
        seed_documents.run_seed(db_session, embed_fn=always_fails)

    assert db_session.query(Document).filter(Document.title == failing_title).one_or_none() is None
