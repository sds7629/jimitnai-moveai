"""Tests for the POST /incidents/{id}/simulate + GET /incidents/{id}/candidates
API endpoints (app/api/simulate.py) -- the pipeline entry point that wires
response-design -> constraint-validation -> simulation together.

Covers:
  1. A brand-new incident: stage 1 creates candidates, stage 2 validates
     them, stage 3 simulates the eligible ones; GET /candidates then shows
     validation status + the latest simulation result in one response
     (the shape the frontend's "대응안 비교 카드" needs).
  2. An incident that already has candidates (here: one of the 3 seeded
     scenarios, which db/init/003-seed-scenarios.sql seeds directly) is
     detected and candidate generation is skipped
     (reused_existing_candidates=True) -- re-running /simulate must not
     duplicate the seeded baseline/active candidate rows, but must still
     append a fresh simulation_results row each time (append-only
     re-simulation).
  3. 404 for an unknown incident, 409 for a non-'유효' (e.g. duplicate)
     incident.

The two LLM-calling stages are faked by monkeypatching
`get_llm_provider` where each service module looks it up (the API layer
never passes an explicit llm_provider, so this is the only way to keep the
whole call chain off the network/API key).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.llm import LLMConfigError
from app.main import app

client = TestClient(app)
_RUN_ID = uuid.uuid4().hex[:8]


class _FakeCandidateProvider:
    def generate(self, prompt, *, system=None, temperature=0.7):
        return json.dumps(
            {
                "candidates": [
                    {
                        "response_category": "컨테이너 우선반출",
                        "candidate_type": "단일",
                        "description": "컨테이너 우선 반출 슬롯 확보",
                        "preconditions": [],
                        "start_time_variant": "now",
                        "reference_document_ids": [],
                    }
                ]
            }
        )


class _FakeSimProvider:
    def generate(self, prompt, *, system=None, temperature=0.7):
        return json.dumps(
            {
                "expected_loss": 1_500_000,
                "p90": 3_000_000,
                "cvar": 3_500_000,
                "confidence": 0.65,
                "sensitivity_variables": ["안전재고 소진 속도"],
                "fact": {"qty": 480},
                "inference": {"depletion_hours": 14},
                "assumption": {"consumption_rate": "steady"},
            }
        )


@pytest.fixture(autouse=True)
def _fake_llm_and_embeddings(monkeypatch):
    monkeypatch.setattr("app.rag.search.embed_text", lambda _text: [0.0] * 768)
    monkeypatch.setattr("app.services.response_design.get_llm_provider", lambda: _FakeCandidateProvider())
    monkeypatch.setattr("app.services.simulation.get_llm_provider", lambda: _FakeSimProvider())


def _loc(base: str) -> str:
    return f"{base} ({_RUN_ID})"


def _create_incident(type_: str, location: str) -> dict:
    # Unique container id per incident -- constraint-validation's
    # cross-incident overlap heuristic (app/services/constraint_validation.py)
    # would otherwise flag unrelated test incidents against each other, both
    # within one run and across repeated runs against the same persistent
    # dev DB (response_candidates/incidents have no delete()).
    unique_container = f"CTN-API-{uuid.uuid4().hex[:8]}"
    occurred_at = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "type": type_,
        "location": _loc(location),
        "occurred_at": occurred_at.isoformat(),
        "affected_targets": {
            "containers": [unique_container],
            "parts": ["PT-API-1"],
            "production_orders": ["PO-API-1"],
            "customers": ["Dealer-API-1"],
        },
    }
    resp = client.post("/incidents", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ------------------------------------------------------------------
# 1. Fresh incident: full pipeline runs end-to-end
# ------------------------------------------------------------------


def test_simulate_pipeline_runs_end_to_end_for_new_incident():
    incident = _create_incident("항만 적체", "API신규파이프라인")

    resp = client.post(f"/incidents/{incident['id']}/simulate")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["incident_id"] == incident["id"]
    assert body["reused_existing_candidates"] is False
    assert body["candidate_count"] >= 2  # baseline + at least 1 LLM candidate
    assert body["validated_count"] == body["candidate_count"]
    assert body["simulated_count"] >= 1

    candidates_resp = client.get(f"/incidents/{incident['id']}/candidates")
    assert candidates_resp.status_code == 200, candidates_resp.text
    candidates_body = candidates_resp.json()

    assert candidates_body["incident_id"] == incident["id"]
    assert len(candidates_body["candidates"]) == body["candidate_count"]

    baseline = next(c for c in candidates_body["candidates"] if c["candidate_type"] == "baseline")
    assert baseline["validation_status"] == "가능"
    assert baseline["latest_simulation"] is not None
    assert baseline["latest_simulation"]["fact"]
    assert baseline["latest_simulation"]["inference"]
    assert baseline["latest_simulation"]["assumption"]

    # Any 불가능 candidate must always carry a reason (none expected here,
    # but the response contract must expose the fields either way).
    for c in candidates_body["candidates"]:
        if c["validation_status"] == "불가능":
            assert c["exclusion_category"]
            assert c["exclusion_detail"]


# ------------------------------------------------------------------
# 2. Re-run policy: existing candidates (seeded scenario) are reused,
#    not duplicated; re-simulation still appends new results.
# ------------------------------------------------------------------


def test_simulate_reuses_existing_candidates_for_seeded_incident(db_session):
    row = db_session.execute(text("SELECT incident_id FROM seed_scenarios WHERE scenario_key = '적체'")).one()
    incident_id = row[0]

    before = client.get(f"/incidents/{incident_id}/candidates").json()
    candidate_count_before = len(before["candidates"])
    assert candidate_count_before == 2  # baseline + 1 active, seeded directly by db/init

    resp = client.post(f"/incidents/{incident_id}/simulate")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reused_existing_candidates"] is True
    assert body["candidate_count"] == candidate_count_before  # no duplicates created

    after_first = client.get(f"/incidents/{incident_id}/candidates").json()
    assert len(after_first["candidates"]) == candidate_count_before
    first_sim_ids = {
        c["latest_simulation"]["id"] for c in after_first["candidates"] if c["latest_simulation"]
    }
    assert first_sim_ids  # at least one simulation result now exists

    # Re-run: still no new candidates, but a fresh simulation_results row
    # per eligible candidate (append-only -- old rows untouched).
    resp2 = client.post(f"/incidents/{incident_id}/simulate")
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    assert body2["reused_existing_candidates"] is True
    assert body2["candidate_count"] == candidate_count_before

    after_second = client.get(f"/incidents/{incident_id}/candidates").json()
    second_sim_ids = {
        c["latest_simulation"]["id"] for c in after_second["candidates"] if c["latest_simulation"]
    }
    assert second_sim_ids.isdisjoint(first_sim_ids)  # brand-new rows, not updates of the old ones


# ------------------------------------------------------------------
# 3. 404 / 409
# ------------------------------------------------------------------


def test_simulate_endpoint_404s_for_unknown_incident():
    resp = client.post("/incidents/999999999/simulate")
    assert resp.status_code == 404


def test_candidates_endpoint_404s_for_unknown_incident():
    resp = client.get("/incidents/999999999/candidates")
    assert resp.status_code == 404


def test_simulate_endpoint_503s_when_llm_not_configured(monkeypatch):
    # LLMConfigError (e.g. GEMINI_API_KEY unset) must surface as a clean
    # 503 with a readable detail message -- not an unhandled 500. This is
    # a real gap the orchestrator found during pre-merge review: the API
    # layer caught ResponseGenerationError/SimulationValidationError (bad
    # LLM *responses*) but not LLMConfigError (LLM not *configured* at
    # all), which are raised directly by get_llm_provider() before any
    # response is even attempted.
    def _raise_config_error():
        raise LLMConfigError("GEMINI_API_KEY가 설정되지 않았습니다.")

    monkeypatch.setattr("app.services.response_design.get_llm_provider", _raise_config_error)

    incident = _create_incident("항만 적체", "API-LLM미설정")
    resp = client.post(f"/incidents/{incident['id']}/simulate")
    assert resp.status_code == 503
    assert "GEMINI_API_KEY" in resp.json()["detail"]


def test_simulate_endpoint_409s_for_non_eligible_incident():
    occurred_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    base_payload = {
        "type": "항만 적체",
        "location": _loc("API-409대상"),
        "occurred_at": occurred_at.isoformat(),
        "affected_targets": {"containers": ["CTN-API-DUP"]},
    }
    first = client.post("/incidents", json=base_payload)
    assert first.status_code == 201
    second_payload = {**base_payload, "occurred_at": (occurred_at + timedelta(minutes=10)).isoformat()}
    second = client.post("/incidents", json=second_payload)
    assert second.status_code == 201
    assert second.json()["status"] == "중복"

    resp = client.post(f"/incidents/{second.json()['id']}/simulate")
    assert resp.status_code == 409
