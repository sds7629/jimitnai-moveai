"""Tests for the constraint-validation agent (agents/constraint-validation.md).

Covers the DoD's minimum 3 cases plus edge cases:
  1. Normal pass (a candidate with no detectable resource conflict -> 가능).
  2. Resource shortage (a full transport stoppage, e.g. the 파업 scenario's
     하역중단 status) excludes the candidate with an exclusion category +
     detail -- never silently.
  3. Conditional pass (a pending-but-not-fully-blocked transport status,
     e.g. the 적체 scenario's 반출대기) yields 조건부 with preconditions
     attached.

Plus: baseline always passes regardless of scenario, and the cross-incident
resource-overlap heuristic marks a second incident's candidate infeasible
when it references a container another *already-validated* active
incident's candidate also claims.

No LLM call is involved in this stage at all (see module docstring in
app/services/constraint_validation.py), so these tests only need
response-design's generate_candidates (with a scripted fake provider) to
set candidates up, plus a fake embed_fn for the RAG call inside it.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.response_candidates import ResponseCandidateRepository
from app.services.constraint_validation import validate_candidates
from app.services.operational_graph import IncidentNotFoundError
from app.services.response_design import generate_candidates

client = TestClient(app)
_RUN_ID = uuid.uuid4().hex[:8]


@pytest.fixture(autouse=True)
def _fake_embeddings(monkeypatch):
    monkeypatch.setattr("app.rag.search.embed_text", lambda _text: [0.0] * 768)


class ScriptedProvider:
    def __init__(self, responses: list[str]):
        self._responses = responses
        self.call_count = 0

    def generate(self, prompt: str, *, system=None, temperature: float = 0.7) -> str:
        self.call_count += 1
        idx = min(self.call_count - 1, len(self._responses) - 1)
        return self._responses[idx]


def _loc(base: str) -> str:
    return f"{base} ({_RUN_ID})"


def _create_incident(type_: str, location: str, containers: list[str]) -> dict:
    occurred_at = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "type": type_,
        "location": _loc(location),
        "occurred_at": occurred_at.isoformat(),
        "affected_targets": {
            "containers": containers,
            "parts": ["PT-CV-1"],
            "production_orders": ["PO-CV-1"],
            "customers": ["Dealer-CV-1"],
        },
    }
    resp = client.post("/incidents", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _one_candidate(description: str, container_id: str | None = None) -> str:
    desc = description if container_id is None else f"{description} ({container_id} 대상)"
    return json.dumps(
        {
            "candidates": [
                {
                    "response_category": "컨테이너 우선반출",
                    "candidate_type": "단일",
                    "description": desc,
                    "preconditions": [],
                    "start_time_variant": "now",
                    "reference_document_ids": [],
                }
            ]
        }
    )


# ------------------------------------------------------------------
# 1. Normal pass
# ------------------------------------------------------------------


def test_candidate_with_no_resource_conflict_passes(db_session):
    # A generic candidate that mentions no transport/inventory keyword at
    # all (e.g. a customer-priority change) has nothing for either resource
    # rule to flag, so it defaults to 가능.
    incident = _create_incident("항만 적체", "정상통과", [f"CTN-CV-NORMAL-{_RUN_ID}"])
    provider = ScriptedProvider(
        [
            json.dumps(
                {
                    "candidates": [
                        {
                            "response_category": "고객출고우선순위",
                            "candidate_type": "단일",
                            "description": "고객별 출고 우선순위를 재조정",
                            "preconditions": [],
                            "start_time_variant": "now",
                            "reference_document_ids": [],
                        }
                    ]
                }
            )
        ]
    )
    asyncio.run(generate_candidates(db_session, incident["id"], llm_provider=provider))

    validated = validate_candidates(db_session, incident["id"])

    non_baseline = [c for c in validated if c.candidate_type != "baseline"]
    assert len(non_baseline) == 1
    assert non_baseline[0].validation_status == "가능"
    assert non_baseline[0].exclusion_category is None
    assert non_baseline[0].exclusion_detail is None


# ------------------------------------------------------------------
# 2. Resource shortage -> excluded with reason
# ------------------------------------------------------------------


def test_full_transport_stoppage_excludes_candidate_with_reason(db_session):
    # 항만 파업 scenario seeds transport status '하역중단' (a full stop --
    # see app/services/operational_graph.py SCENARIO_TEMPLATES['파업']).
    incident = _create_incident("항만 파업", "자원부족제외", [f"CTN-CV-STRIKE-{_RUN_ID}"])
    provider = ScriptedProvider([_one_candidate("컨테이너 우선반출 시도")])
    asyncio.run(generate_candidates(db_session, incident["id"], llm_provider=provider))

    validated = validate_candidates(db_session, incident["id"])

    non_baseline = [c for c in validated if c.candidate_type != "baseline"]
    assert len(non_baseline) == 1
    candidate = non_baseline[0]
    assert candidate.validation_status == "불가능"
    assert candidate.exclusion_category == "자원부족"
    assert candidate.exclusion_detail  # a reason must always be present
    assert "하역중단" in candidate.exclusion_detail


# ------------------------------------------------------------------
# 3. Conditional pass with preconditions
# ------------------------------------------------------------------


def test_pending_transport_status_yields_conditional_pass_with_preconditions(db_session):
    # 항만 적체 scenario seeds transport status '반출대기' (delayed, but not
    # a full stop) -- see SCENARIO_TEMPLATES['적체'].
    incident = _create_incident("항만 적체", "조건부통과", [f"CTN-CV-PENDING-{_RUN_ID}"])
    provider = ScriptedProvider([_one_candidate("컨테이너 우선반출 시도")])
    asyncio.run(generate_candidates(db_session, incident["id"], llm_provider=provider))

    validated = validate_candidates(db_session, incident["id"])

    non_baseline = [c for c in validated if c.candidate_type != "baseline"]
    assert len(non_baseline) == 1
    candidate = non_baseline[0]
    assert candidate.validation_status == "조건부"
    assert candidate.exclusion_category is None
    assert candidate.preconditions  # precondition(s) must be attached
    assert any("승인" in p for p in candidate.preconditions)


# ------------------------------------------------------------------
# Baseline always passes, regardless of scenario
# ------------------------------------------------------------------


def test_baseline_always_passes_even_under_full_stoppage(db_session):
    incident = _create_incident("항만 파업", "baseline항상가능", [f"CTN-CV-STRIKE-BASE-{_RUN_ID}"])
    provider = ScriptedProvider([_one_candidate("긴급운송 시도")])
    asyncio.run(generate_candidates(db_session, incident["id"], llm_provider=provider))

    validated = validate_candidates(db_session, incident["id"])

    baseline = next(c for c in validated if c.candidate_type == "baseline")
    assert baseline.validation_status == "가능"
    assert baseline.exclusion_category is None
    assert baseline.exclusion_detail is None


# ------------------------------------------------------------------
# Cross-incident resource overlap heuristic
# ------------------------------------------------------------------


def test_cross_incident_container_overlap_excludes_the_later_candidate(db_session):
    shared_container = f"CTN-SHARED-{_RUN_ID}"

    incident_a = _create_incident("관세 규정 변경", "자원중복A", [f"CTN-CV-A-{_RUN_ID}"])
    provider_a = ScriptedProvider([_one_candidate("대체 통관경로 확보", shared_container)])
    asyncio.run(generate_candidates(db_session, incident_a["id"], llm_provider=provider_a))
    validate_candidates(db_session, incident_a["id"])  # incident_a's candidate becomes 가능

    repo = ResponseCandidateRepository(db_session)
    candidate_a = next(c for c in repo.for_incident(incident_a["id"]) if c.candidate_type != "baseline")
    assert candidate_a.validation_status in ("가능", "조건부")

    incident_b = _create_incident("관세 규정 변경", "자원중복B", [f"CTN-CV-B-{_RUN_ID}"])
    provider_b = ScriptedProvider([_one_candidate("동일 컨테이너로 대체 통관경로 확보", shared_container)])
    asyncio.run(generate_candidates(db_session, incident_b["id"], llm_provider=provider_b))
    validated_b = validate_candidates(db_session, incident_b["id"])

    candidate_b = next(c for c in validated_b if c.candidate_type != "baseline")
    assert candidate_b.validation_status == "불가능"
    assert candidate_b.exclusion_category == "자원부족"
    assert str(incident_a["id"]) in candidate_b.exclusion_detail or f"#{incident_a['id']}" in candidate_b.exclusion_detail


# ------------------------------------------------------------------
# Not-found
# ------------------------------------------------------------------


def test_validate_candidates_raises_not_found_for_unknown_incident(db_session):
    with pytest.raises(IncidentNotFoundError):
        validate_candidates(db_session, 999999999)


def test_validate_candidates_returns_empty_list_when_no_candidates_yet(db_session):
    incident = _create_incident("항만 적체", "후보없음", [f"CTN-CV-NONE-{_RUN_ID}"])
    # No generate_candidates call -- stage 1 has not run yet.
    assert validate_candidates(db_session, incident["id"]) == []
