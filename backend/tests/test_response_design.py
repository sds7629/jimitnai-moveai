"""Tests for the response-design agent (agents/response-design.md).

Covers the DoD's minimum 3 cases plus edge cases:
  1. Normal candidate generation (baseline + LLM candidates, each carrying
     reference-document evidence).
  2. Baseline is never missing, even when the LLM returns zero candidates.
  3. RAG returning 0 hits does not block candidate generation, and forces
     reference_document_ids=[] even if the LLM hallucinates ids.

Plus: an LLM response that can't be parsed as JSON is retried once and then
raises a clear error, and the now/+6h start-time-variant pair is guaranteed
even if the LLM ignores that instruction.

No real GEMINI_API_KEY / network call is ever exercised: `llm_provider` is
always a fake object, and `app.rag.search.embed_text` is monkeypatched so
the (real) pgvector search path runs without needing a real embedding call.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.llm.gemini_embeddings import EMBEDDING_DIM
from app.main import app
from app.repositories.documents import DocumentChunkRepository, DocumentRepository
from app.repositories.response_candidates import ResponseCandidateRepository
from app.services.operational_graph import IncidentNotEligibleError, IncidentNotFoundError
from app.services.response_design import (
    ALLOWED_LLM_CANDIDATE_TYPES,
    BASELINE_CANDIDATE_TYPE,
    ResponseGenerationError,
    generate_candidates,
)

client = TestClient(app)
_RUN_ID = uuid.uuid4().hex[:8]
# A one-hot vector, not an all-zero one: documents/document_chunks have no
# delete() (agents/knowledge-retrieval.md), so the dev DB accumulates chunks
# across every previous run of this file. An all-zero fake embedding makes
# pgvector cosine-distance ordering degenerate/tied once enough chunks pile
# up, so top_k can silently drop the one chunk a test actually cares about.
# A run-unique one-hot vector keeps this run's target chunk's distance to
# its own query at exactly 0, guaranteed closer than any pre-existing chunk.
_EMBED_INDEX = int(_RUN_ID, 16) % EMBEDDING_DIM


def _one_hot() -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    vec[_EMBED_INDEX] = 1.0
    return vec


@pytest.fixture(autouse=True)
def _fake_embeddings(monkeypatch):
    # No real GEMINI_API_KEY in this sandbox -- fake the embedding step so
    # search_similar_chunks's real pgvector query still runs end-to-end.
    monkeypatch.setattr("app.rag.search.embed_text", lambda _text: _one_hot())


class ScriptedProvider:
    """Fake LLMProvider returning canned responses in order (last one is
    reused for any extra calls beyond the list)."""

    def __init__(self, responses: list[str]):
        self._responses = responses
        self.call_count = 0

    def generate(self, prompt: str, *, system=None, temperature: float = 0.7) -> str:
        self.call_count += 1
        idx = min(self.call_count - 1, len(self._responses) - 1)
        return self._responses[idx]


def _loc(base: str) -> str:
    return f"{base} ({_RUN_ID})"


def _create_incident(type_: str, location: str, containers=None, parts=None) -> dict:
    occurred_at = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "type": type_,
        "location": _loc(location),
        "occurred_at": occurred_at.isoformat(),
        "affected_targets": {
            "containers": containers or ["CTN-RD-1"],
            "parts": parts or ["PT-RD-1"],
            "production_orders": ["PO-RD-1"],
            "customers": ["Dealer-RD-1"],
        },
    }
    resp = client.post("/incidents", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _candidates_json(candidates: list[dict]) -> str:
    return json.dumps({"candidates": candidates})


# ------------------------------------------------------------------
# 1. Normal candidate generation
# ------------------------------------------------------------------


def test_generate_candidates_produces_baseline_plus_llm_candidates_with_evidence(db_session):
    incident = _create_incident("항만 적체", "정상생성")

    doc_repo = DocumentRepository(db_session)
    chunk_repo = DocumentChunkRepository(db_session)
    doc = doc_repo.add(doc_type="플레이북", title=f"컨테이너 우선반출 플레이북 ({_RUN_ID})", source="test")
    chunk_repo.add(
        document_id=doc.id, chunk_text="컨테이너 우선반출 절차", chunk_type="대응패턴", embedding=_one_hot()
    )

    provider = ScriptedProvider(
        [
            _candidates_json(
                [
                    {
                        "response_category": "컨테이너 우선반출",
                        "candidate_type": "단일",
                        "description": "CTN-RD-1 우선 반출 슬롯 확보",
                        "preconditions": ["항만 승인 필요"],
                        "start_time_variant": "now",
                        "reference_document_ids": [doc.id],
                    },
                    {
                        "response_category": "긴급운송",
                        "candidate_type": "단일",
                        "description": "항공 긴급운송으로 대체 조달",
                        "preconditions": [],
                        "start_time_variant": "+6h",
                        "reference_document_ids": [],
                    },
                ]
            )
        ]
    )

    candidates = asyncio.run(generate_candidates(db_session, incident["id"], llm_provider=provider))

    assert len(candidates) == 3  # baseline + 2 LLM candidates
    baseline = [c for c in candidates if c.candidate_type == BASELINE_CANDIDATE_TYPE]
    assert len(baseline) == 1
    assert baseline[0].validation_status == "미검증"

    llm_candidates = [c for c in candidates if c.candidate_type != BASELINE_CANDIDATE_TYPE]
    assert len(llm_candidates) == 2
    for c in llm_candidates:
        assert c.candidate_type in ALLOWED_LLM_CANDIDATE_TYPES
        assert c.validation_status == "미검증"

    with_evidence = next(c for c in llm_candidates if "컨테이너" in c.description)
    assert with_evidence.reference_document_ids == [doc.id]
    assert "컨테이너 우선반출" in with_evidence.description  # response_category folded into description


# ------------------------------------------------------------------
# 2. Baseline is never missing
# ------------------------------------------------------------------


def test_baseline_present_even_when_llm_returns_zero_candidates(db_session):
    incident = _create_incident("항만 적체", "baseline항상포함-빈응답")
    provider = ScriptedProvider([_candidates_json([])])

    candidates = asyncio.run(generate_candidates(db_session, incident["id"], llm_provider=provider))

    assert len(candidates) == 1
    assert candidates[0].candidate_type == BASELINE_CANDIDATE_TYPE
    assert candidates[0].validation_status == "미검증"


def test_baseline_present_across_all_3_seed_scenario_types(db_session):
    for type_ in ("항만 적체", "항만 파업", "관세 규정 변경"):
        incident = _create_incident(type_, f"3종시나리오-{type_}")
        provider = ScriptedProvider([_candidates_json([])])
        candidates = asyncio.run(generate_candidates(db_session, incident["id"], llm_provider=provider))
        assert any(c.candidate_type == BASELINE_CANDIDATE_TYPE for c in candidates)


# ------------------------------------------------------------------
# 3. RAG 0 results does not block generation, and forbids hallucinated refs
# ------------------------------------------------------------------


def test_zero_rag_results_still_generates_candidates_with_empty_reference_ids(db_session):
    incident = _create_incident("항만 적체", "RAG없음")

    # An id that does not correspond to anything RAG actually returned
    # (RAG returns nothing here -- no matching documents were seeded for
    # this doc_type/query in this test's isolated run).
    provider = ScriptedProvider(
        [
            _candidates_json(
                [
                    {
                        "response_category": "생산순서변경",
                        "candidate_type": "단일",
                        "description": "생산 순서를 재배열",
                        "preconditions": [],
                        "start_time_variant": None,
                        "reference_document_ids": [999999999],
                    }
                ]
            )
        ]
    )

    candidates = asyncio.run(generate_candidates(db_session, incident["id"], llm_provider=provider))

    llm_candidates = [c for c in candidates if c.candidate_type != BASELINE_CANDIDATE_TYPE]
    assert len(llm_candidates) >= 1
    assert llm_candidates[0].reference_document_ids == []


# ------------------------------------------------------------------
# Extra: retry-then-error on unparseable LLM JSON
# ------------------------------------------------------------------


def test_unparseable_llm_response_retries_once_then_raises(db_session):
    incident = _create_incident("항만 적체", "파싱실패")
    provider = ScriptedProvider(["이것은 JSON이 아닙니다", "역시 JSON이 아닙니다"])

    with pytest.raises(ResponseGenerationError):
        asyncio.run(generate_candidates(db_session, incident["id"], llm_provider=provider))

    assert provider.call_count == 2  # initial try + exactly 1 retry

    # The baseline candidate is committed before the LLM call and is not
    # rolled back by the later failure -- so it still exists even though
    # the overall call raised.
    baseline = ResponseCandidateRepository(db_session).baseline_for_incident(incident["id"])
    assert baseline is not None


# ------------------------------------------------------------------
# Extra: now/+6h start-time-variant pair is guaranteed
# ------------------------------------------------------------------


def test_start_time_variant_pair_guaranteed_when_llm_omits_it(db_session):
    incident = _create_incident("항만 적체", "착수시점보장")
    provider = ScriptedProvider(
        [
            _candidates_json(
                [
                    {
                        "response_category": "대체항",
                        "candidate_type": "단일",
                        "description": "대체항 활용",
                        "preconditions": [],
                        "start_time_variant": None,
                        "reference_document_ids": [],
                    }
                ]
            )
        ]
    )

    candidates = asyncio.run(generate_candidates(db_session, incident["id"], llm_provider=provider))

    variants = {c.start_time_variant for c in candidates}
    assert "now" in variants
    assert "+6h" in variants


# ------------------------------------------------------------------
# Not-found / not-eligible passthrough from ensure_snapshot_and_dag
# ------------------------------------------------------------------


def test_generate_candidates_raises_not_found_for_unknown_incident(db_session):
    with pytest.raises(IncidentNotFoundError):
        asyncio.run(generate_candidates(db_session, 999999999, llm_provider=ScriptedProvider(["{}"])))


def test_generate_candidates_raises_not_eligible_for_duplicate_incident(db_session):
    occurred_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    base_payload = {
        "type": "항만 적체",
        "location": _loc("중복사건-생성불가"),
        "occurred_at": occurred_at.isoformat(),
        "affected_targets": {"containers": ["CTN-RD-DUP"]},
    }
    first = client.post("/incidents", json=base_payload)
    assert first.status_code == 201
    second_payload = {**base_payload, "occurred_at": (occurred_at + timedelta(minutes=10)).isoformat()}
    second = client.post("/incidents", json=second_payload)
    assert second.status_code == 201
    assert second.json()["status"] == "중복"

    with pytest.raises(IncidentNotEligibleError):
        asyncio.run(
            generate_candidates(db_session, second.json()["id"], llm_provider=ScriptedProvider(["{}"]))
        )
