"""Tests for the incident-intake entry point (agents/incident-intake.md).

Covers the DoD's minimum 3 cases plus edge cases:
  1. Normal creation for each of the 3 seed scenario shapes (congestion,
     strike, tariff).
  2. Duplicate incident detection (and that it's audited).
  3. Missing required-ish input (affected_targets) becoming an explicit
     assumption, persisted verbatim into incidents.assumptions.

Plus: status-filtered listing, invalid-status rejection, 422 on missing
hard-required fields, and the mandatory-reason dismiss (오탐) flow.

These hit the real app + real Postgres (docker compose's `db` service),
matching the existing test_health.py / test_append_only.py style — no
mocking of the DB layer.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.audit_log import AuditLogRepository
from app.repositories.incidents import IncidentRepository

client = TestClient(app)

# The dedup window (12h, see app/services/incident_intake.py) is based on
# occurred_at proximity only, not creation time -- so re-running this suite
# against the same persistent dev DB with a fixed location string would let
# a *previous* run's row (same type/location, nearly the same "now - N days"
# occurred_at) get picked up as a "duplicate" of this run's row. A per-run
# random suffix on every test-owned location keeps runs isolated from each
# other without needing to delete anything (incidents has no delete()).
_RUN_ID = uuid.uuid4().hex[:8]


def _loc(base: str) -> str:
    return f"{base} ({_RUN_ID})"


def _iso(dt: datetime) -> str:
    return dt.isoformat()


SEED_SCENARIO_PAYLOADS = [
    {
        "type": "항만 적체",
        "location": _loc("부산항 3부두"),
        "affected_targets": {
            "containers": ["CTN-9001"],
            "parts": ["PT-ENGINE-01"],
            "production_orders": ["PO-2026-9001"],
            "customers": ["Dealer-Test-01"],
        },
    },
    {
        "type": "항만 파업",
        "location": _loc("부산항"),
        "affected_targets": {
            "containers": ["CTN-9002"],
            "parts": ["PT-BATTERY-01"],
            "production_orders": ["PO-2026-9002"],
            "customers": ["Dealer-Test-02"],
        },
    },
    {
        "type": "관세 규정 변경",
        "location": _loc("인천세관"),
        "affected_targets": {
            "containers": ["CTN-9003"],
            "parts": ["PT-CHIP-01"],
            "production_orders": ["PO-2026-9003"],
            "customers": ["Dealer-Test-03"],
        },
    },
]


@pytest.mark.parametrize("scenario", SEED_SCENARIO_PAYLOADS, ids=["congestion", "strike", "tariff"])
def test_create_incident_for_each_seed_scenario(scenario, db_session):
    # occurred_at set far enough in the past that it can never collide with
    # the actual seeded incidents (which are all "a few hours ago" per
    # db/init/003-seed-scenarios.sql) inside the duplicate-detection window.
    occurred_at = datetime.now(timezone.utc) - timedelta(days=3)
    body = {**scenario, "occurred_at": _iso(occurred_at)}

    resp = client.post("/incidents", json=body)

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["type"] == scenario["type"]
    assert data["location"] == scenario["location"]
    assert data["status"] == "유효"
    assert data["duplicate_of_incident_id"] is None
    assert data["missing_fields"] == []
    assert data["affected_targets"]["containers"] == scenario["affected_targets"]["containers"]

    # No silent classification -- an audited reason must exist.
    audit_repo = AuditLogRepository(db_session)
    timeline = audit_repo.timeline_for_incident(data["id"])
    created_events = [e for e in timeline if e.event_type == "incident_created"]
    assert len(created_events) == 1
    assert created_events[0].reason


def test_duplicate_incident_is_flagged_and_audited(db_session):
    occurred_at = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "type": "항만 적체",
        "location": _loc("부산항 3부두 중복테스트"),
        "occurred_at": _iso(occurred_at),
        "affected_targets": {"containers": ["CTN-DUP-1"]},
    }

    first = client.post("/incidents", json=payload)
    assert first.status_code == 201
    first_id = first.json()["id"]
    assert first.json()["status"] == "유효"

    # Same type + location, occurred_at 30 min later -> within the proximity
    # window -> must be classified as a duplicate of the first.
    second_payload = {**payload, "occurred_at": _iso(occurred_at + timedelta(minutes=30))}
    second = client.post("/incidents", json=second_payload)

    assert second.status_code == 201
    second_data = second.json()
    assert second_data["status"] == "중복"
    assert second_data["duplicate_of_incident_id"] == first_id
    assert second_data["duplicate_detected"] is True

    audit_repo = AuditLogRepository(db_session)
    timeline = audit_repo.timeline_for_incident(second_data["id"])
    dup_events = [e for e in timeline if e.event_type == "duplicate_detected"]
    assert len(dup_events) == 1
    assert dup_events[0].reason  # judgement basis must be recorded, not silent
    assert dup_events[0].payload["duplicate_of_incident_id"] == first_id


def test_duplicate_detection_ignores_events_far_apart_in_time():
    occurred_at = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "type": "항만 적체",
        "location": _loc("부산항 3부두 원거리테스트"),
        "occurred_at": _iso(occurred_at),
    }
    first = client.post("/incidents", json=payload)
    assert first.status_code == 201

    far_payload = {**payload, "occurred_at": _iso(occurred_at - timedelta(days=10))}
    second = client.post("/incidents", json=far_payload)

    assert second.status_code == 201
    assert second.json()["status"] == "유효"
    assert second.json()["duplicate_of_incident_id"] is None


def test_missing_affected_targets_recorded_as_assumption(db_session):
    occurred_at = datetime.now(timezone.utc) - timedelta(days=1)
    payload = {
        "type": "자유입력 사건",
        "location": _loc("평택항"),
        "occurred_at": _iso(occurred_at),
        # affected_targets intentionally omitted entirely
    }

    resp = client.post("/incidents", json=payload)

    assert resp.status_code == 201
    data = resp.json()
    assert data["missing_fields"] == ["affected_targets"]
    assert len(data["assumptions"]) == 1
    assert "ASSUMPTION" in data["assumptions"][0]

    # Persisted verbatim into incidents.assumptions -- this is the interface
    # the operational-graph wave reads from when building its own snapshot
    # assumptions list (agents/incident-intake.md work item #4).
    repo = IncidentRepository(db_session)
    persisted = repo.get(data["id"])
    assert persisted.assumptions == data["assumptions"]


def test_partial_affected_targets_reports_only_missing_subfields():
    occurred_at = datetime.now(timezone.utc) - timedelta(days=1, hours=2)
    payload = {
        "type": "자유입력 사건",
        "location": _loc("울산항"),
        "occurred_at": _iso(occurred_at),
        "affected_targets": {"containers": ["CTN-P1"]},
    }

    resp = client.post("/incidents", json=payload)

    assert resp.status_code == 201
    data = resp.json()
    assert "affected_targets.containers" not in data["missing_fields"]
    assert "affected_targets.parts" in data["missing_fields"]
    assert "affected_targets.production_orders" in data["missing_fields"]
    assert "affected_targets.customers" in data["missing_fields"]


def test_create_incident_missing_required_field_returns_422():
    resp = client.post(
        "/incidents",
        json={"location": "어딘가", "occurred_at": _iso(datetime.now(timezone.utc))},
    )
    assert resp.status_code == 422


def test_list_incidents_filters_by_status_query_param():
    resp = client.get("/incidents", params={"status": "유효"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 3  # at least the 3 seed scenarios
    assert all(item["status"] == "유효" for item in data)


def test_list_incidents_rejects_invalid_status():
    resp = client.get("/incidents", params={"status": "존재하지않는상태"})
    assert resp.status_code == 400


def test_dismiss_requires_reason(db_session):
    occurred_at = datetime.now(timezone.utc) - timedelta(days=2)
    create_resp = client.post(
        "/incidents",
        json={
            "type": "오탐테스트",
            "location": _loc("오탐위치"),
            "occurred_at": _iso(occurred_at),
        },
    )
    incident_id = create_resp.json()["id"]

    missing_reason = client.post(f"/incidents/{incident_id}/dismiss", json={"actor": "operator-1"})
    assert missing_reason.status_code == 422

    with_reason = client.post(
        f"/incidents/{incident_id}/dismiss",
        json={"reason": "현장 확인 결과 실제 영향 없음", "actor": "operator-1"},
    )
    assert with_reason.status_code == 200
    assert with_reason.json()["status"] == "오탐"

    audit_repo = AuditLogRepository(db_session)
    timeline = audit_repo.timeline_for_incident(incident_id)
    dismiss_events = [e for e in timeline if e.event_type == "false_positive_dismissed"]
    assert len(dismiss_events) == 1
    assert dismiss_events[0].reason == "현장 확인 결과 실제 영향 없음"


def test_dismiss_unknown_incident_returns_404():
    resp = client.post("/incidents/999999999/dismiss", json={"reason": "사유", "actor": "operator-1"})
    assert resp.status_code == 404
