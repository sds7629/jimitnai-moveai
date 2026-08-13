"""Tests for the execution-tracking agent (agents/execution-tracking.md) --
app/services/execution_tracking.py + PATCH /sop/{sop_id}/status +
GET /incidents/{id}/timeline.

Covers the DoD's minimum cases:
  1. 정상 상태 전이 기록 -- 이력으로 남고 덮어써지지 않음(append-only).
  2. 기한 초과 미수락이 편차로 감지됨(detect_deviation).
  3. 편차 감지 시 오케스트레이션 함수(handle_execution_deviation) 호출 신호가
     발생함 -- 직접 재시뮬레이션하지 않는다는 것을 모킹으로 확인.
  4. 계획 범위 내 정상 진행 시 편차 미발생.

Plus: PATCH의 404/400 가드, '실패' 상태가 즉시 재평가를 위임하는 경로를 실제
오케스트레이션 파이프라인(가짜 LLM)으로 끝까지 실행해보는 통합 테스트, 그리고
GET /incidents/{id}/timeline이 편차/에스컬레이션 이벤트를 구분 가능한 배열로
반환하는지.

Same LLM-faking pattern as tests/test_orchestration.py / test_communication_sop.py
-- no real network call anywhere in this file.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.audit_log import AuditLogRepository
from app.repositories.decision_packages import DecisionPackageRepository
from app.repositories.incidents import IncidentRepository
from app.repositories.operational_snapshots import OperationalSnapshotRepository
from app.repositories.simulation_results import SimulationResultRepository
from app.services.execution_tracking import (
    STATUS_TRANSITION_EVENT_TYPE,
    InvalidSopStatusError,
    SopNotFoundError,
    check_and_handle_deviation,
    detect_deviation,
    record_status_transition,
)

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
                        "description": "컨테이너 우선 반출 슬롯 확보 및 대체 경로 확보",
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


class _FakeReviewProvider:
    """Fake for stage 4 (다중 관점 교차검증, app/services/candidate_review.py)
    -- this test file doesn't exercise review content, just needs
    POST /incidents/{id}/simulate's new stage 4 to succeed without a real
    LLM call."""

    def generate(self, prompt, *, system=None, temperature=0.7):
        return json.dumps({"concern_level": "low", "comment": "자동화된 교차검증 코멘트", "flags": []})


@pytest.fixture(autouse=True)
def _fake_llm_and_embeddings(monkeypatch):
    monkeypatch.setattr("app.rag.search.embed_text", lambda _text: [0.0] * 768)
    monkeypatch.setattr("app.services.response_design.get_llm_provider", lambda: _FakeCandidateProvider())
    monkeypatch.setattr("app.services.simulation.get_llm_provider", lambda: _FakeSimProvider())
    monkeypatch.setattr("app.services.candidate_review.get_llm_provider", lambda: _FakeReviewProvider())


def _loc(base: str) -> str:
    return f"{base} ({_RUN_ID}-{uuid.uuid4().hex[:6]})"


def _create_and_simulate_incident(type_: str, location: str) -> dict:
    """Same full pipeline setup as tests/test_communication_sop.py --
    incident -> snapshot/DAG -> candidates -> validation -> simulation ->
    decision-package, so dispatch_sop/execution-tracking have a realistic
    precondition to work against."""

    unique_container = f"CTN-EXEC-{uuid.uuid4().hex[:8]}"
    occurred_at = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "type": type_,
        "location": _loc(location),
        "occurred_at": occurred_at.isoformat(),
        "affected_targets": {
            "containers": [unique_container],
            "parts": ["PT-EXEC-1"],
            "production_orders": ["PO-EXEC-1"],
            "customers": ["Dealer-EXEC-1"],
        },
    }
    resp = client.post("/incidents", json=payload)
    assert resp.status_code == 201, resp.text
    incident = resp.json()

    sim_resp = client.post(f"/incidents/{incident['id']}/simulate")
    assert sim_resp.status_code == 200, sim_resp.text

    dp_resp = client.get(f"/incidents/{incident['id']}/decision-package")
    assert dp_resp.status_code == 200, dp_resp.text

    return incident


def _approve(incident_id: int, decision_type: str = "승인", reason: str = "손실 최소화를 위해 즉시 진행") -> dict:
    resp = client.post(
        f"/incidents/{incident_id}/approvals",
        json={"decision_type": decision_type, "reason": reason, "approver": "김담당"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _dispatch_one_sop_id(incident_id: int) -> int:
    """Approve + dispatch SOPs (5 roles), return the first role's sop_id --
    enough for tests that only need one SOP to attach status transitions to."""

    approval = _approve(incident_id)
    dispatch_resp = client.post(f"/approvals/{approval['id']}/dispatch-sop")
    assert dispatch_resp.status_code == 200, dispatch_resp.text
    return dispatch_resp.json()[0]["sop_id"]


def _set_past_deadline(db_session, incident_id: int, hours_ago: float = 2) -> None:
    """Directly append a decision_packages row with a recommended_deadline in
    the past -- same pattern as tests/test_orchestration.py's deadline-overrun
    tests (decision_packages is append-only, so this becomes the new
    "latest" package for the incident without touching the earlier one)."""

    DecisionPackageRepository(db_session).add(
        incident_id=incident_id,
        package={"disclaimer": "test override -- past deadline"},
        recommended_deadline=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )


# ------------------------------------------------------------------
# 1. 정상 상태 전이 기록 -- 이력으로 남고 덮어써지지 않음
# ------------------------------------------------------------------


def test_status_transitions_append_history_without_overwriting(db_session):
    incident = _create_and_simulate_incident("항만 적체", "정상전이케이스")
    sop_id = _dispatch_one_sop_id(incident["id"])

    for status in ("수신", "수락", "시작", "진행", "완료"):
        resp = client.patch(f"/sop/{sop_id}/status", json={"status": status, "actor": "항만담당자"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == status

    transitions = [
        row
        for row in AuditLogRepository(db_session).timeline_for_incident(incident["id"])
        if row.event_type == STATUS_TRANSITION_EVENT_TYPE and row.payload.get("sop_id") == sop_id
    ]
    # All 5 rows persisted -- nothing overwritten -- in the order they were sent.
    assert [row.payload["status"] for row in transitions] == ["수신", "수락", "시작", "진행", "완료"]
    assert len(transitions) == 5

    # GET /incidents/{id}/sop-status (communication-sop's convention) picks
    # these up automatically -- confirms the payload shape matches exactly.
    status_resp = client.get(f"/incidents/{incident['id']}/sop-status")
    assert status_resp.status_code == 200, status_resp.text
    entry = next(s for s in status_resp.json()["sop_statuses"] if s["sop_id"] == sop_id)
    assert entry["status"] == "완료"
    assert entry["received_at"] is not None
    assert entry["accepted_at"] is not None
    assert entry["completed_at"] is not None


def test_record_status_transition_service_returns_404_for_unknown_sop(db_session):
    with pytest.raises(SopNotFoundError):
        record_status_transition(db_session, 999_999_999, "수신", "tester")


def test_record_status_transition_service_returns_400_for_invalid_status(db_session):
    incident = _create_and_simulate_incident("항만 파업", "잘못된상태케이스")
    sop_id = _dispatch_one_sop_id(incident["id"])

    with pytest.raises(InvalidSopStatusError):
        record_status_transition(db_session, sop_id, "완료됨!!", "tester")


def test_patch_sop_status_api_404_and_400(db_session):
    incident = _create_and_simulate_incident("항만 파업", "API가드케이스")
    sop_id = _dispatch_one_sop_id(incident["id"])

    resp_404 = client.patch("/sop/999999999/status", json={"status": "수신", "actor": "tester"})
    assert resp_404.status_code == 404

    resp_400 = client.patch(f"/sop/{sop_id}/status", json={"status": "완료됨!!", "actor": "tester"})
    assert resp_400.status_code == 422  # pydantic schema-level rejection


# ------------------------------------------------------------------
# 2. 기한 초과 미수락이 편차로 감지됨
# ------------------------------------------------------------------


def test_detect_deviation_flags_overdue_unaccepted_sop(db_session):
    incident = _create_and_simulate_incident("항만 적체", "기한초과미수락케이스")
    sop_id = _dispatch_one_sop_id(incident["id"])

    # SOP was only dispatched (never received/accepted) -- push the decision
    # deadline into the past.
    _set_past_deadline(db_session, incident["id"])

    result = detect_deviation(db_session, incident["id"])
    assert result is not None
    assert sop_id in result.related_sop_ids
    assert "기한 내 미수락" in result.reason
    assert sop_id in result.detail["unaccepted_overdue_sop_ids"]


def test_detect_deviation_flags_overdue_incomplete_sop_even_if_accepted(db_session):
    incident = _create_and_simulate_incident("항만 파업", "지연완료케이스")
    sop_id = _dispatch_one_sop_id(incident["id"])

    accept_resp = client.patch(f"/sop/{sop_id}/status", json={"status": "수락", "actor": "운송담당자"})
    assert accept_resp.status_code == 200, accept_resp.text

    _set_past_deadline(db_session, incident["id"])

    result = detect_deviation(db_session, incident["id"])
    assert result is not None
    assert sop_id in result.detail["incomplete_overdue_sop_ids"]
    assert sop_id not in result.detail["unaccepted_overdue_sop_ids"]
    assert "지연된 완료" in result.reason


def test_detect_deviation_returns_none_for_unknown_incident(db_session):
    assert detect_deviation(db_session, 999_999_999) is None


def test_detect_deviation_returns_none_before_any_dispatch(db_session):
    incident = _create_and_simulate_incident("관세 규정 변경", "발송전편차케이스")
    assert detect_deviation(db_session, incident["id"]) is None


# ------------------------------------------------------------------
# 3. 편차 감지 시 오케스트레이션 호출 신호 발생 (직접 재시뮬레이션하지 않음)
# ------------------------------------------------------------------


def test_check_and_handle_deviation_delegates_to_orchestration_without_resimulating_itself(
    db_session, monkeypatch
):
    incident = _create_and_simulate_incident("항만 적체", "위임신호케이스")
    sop_id = _dispatch_one_sop_id(incident["id"])
    _set_past_deadline(db_session, incident["id"])

    calls: list[tuple] = []

    async def _fake_handle_execution_deviation(db, incident_id, deviation_reason, llm_provider=None):
        calls.append((incident_id, deviation_reason, llm_provider))
        return {"faked": True}

    # Patched where execution_tracking looked it up (imported name), not on
    # the orchestration module itself -- confirms execution_tracking calls
    # through this exact reference and never reaches simulate_candidates/
    # ensure_snapshot_and_dag on its own (it doesn't even import them).
    monkeypatch.setattr(
        "app.services.execution_tracking.handle_execution_deviation", _fake_handle_execution_deviation
    )

    simulation_count_before = len(SimulationResultRepository(db_session).for_incident(incident["id"]))
    snapshot_count_before = len(OperationalSnapshotRepository(db_session).history_for_incident(incident["id"]))

    result = asyncio.run(check_and_handle_deviation(db_session, incident["id"]))

    assert result == {"faked": True}
    assert len(calls) == 1
    called_incident_id, called_reason, _ = calls[0]
    assert called_incident_id == incident["id"]
    assert sop_id is not None and str(sop_id) in called_reason or "미수락" in called_reason

    # No real re-simulation/re-snapshot happened -- the fake was the only
    # thing invoked, proving execution_tracking never does that work itself.
    assert len(SimulationResultRepository(db_session).for_incident(incident["id"])) == simulation_count_before
    assert len(OperationalSnapshotRepository(db_session).history_for_incident(incident["id"])) == snapshot_count_before

    # But the detection itself is still recorded in audit_log.
    detected = [
        row
        for row in AuditLogRepository(db_session).timeline_for_incident(incident["id"])
        if row.event_type == "deviation_detected"
    ]
    assert len(detected) == 1


# ------------------------------------------------------------------
# 4. 계획 범위 내 정상 진행 시 편차 미발생
# ------------------------------------------------------------------


def test_no_deviation_within_deadline_and_progressing_normally(db_session):
    incident = _create_and_simulate_incident("관세 규정 변경", "정상진행케이스")
    sop_id = _dispatch_one_sop_id(incident["id"])

    accept_resp = client.patch(f"/sop/{sop_id}/status", json={"status": "수락", "actor": "영업담당자"})
    assert accept_resp.status_code == 200, accept_resp.text

    # Decision package's recommended_deadline was computed from the real DAG
    # (occurred_at 1h ago, scenario durations in the future) -- still ahead
    # of "now", nothing overridden here.
    assert detect_deviation(db_session, incident["id"]) is None
    assert asyncio.run(check_and_handle_deviation(db_session, incident["id"])) is None


def test_no_deviation_once_sop_completed_even_past_deadline(db_session):
    incident = _create_and_simulate_incident("항만 적체", "완료후무편차케이스")
    approval = _approve(incident["id"])
    dispatch_resp = client.post(f"/approvals/{approval['id']}/dispatch-sop")
    assert dispatch_resp.status_code == 200, dispatch_resp.text
    sop_ids = [r["sop_id"] for r in dispatch_resp.json()]

    # Bring every dispatched SOP (all 5 roles) to '완료' -- not just one --
    # so the only thing detect_deviation can observe is "nothing left
    # incomplete", isolating the "완료는 편차가 아니다" behavior from the
    # unrelated "other 4 roles were never even acknowledged" case covered by
    # test_detect_deviation_flags_overdue_unaccepted_sop above.
    for sop_id in sop_ids:
        for status in ("수신", "수락", "완료"):
            resp = client.patch(f"/sop/{sop_id}/status", json={"status": status, "actor": "공장담당자"})
            assert resp.status_code == 200, resp.text

    _set_past_deadline(db_session, incident["id"])

    assert detect_deviation(db_session, incident["id"]) is None


# ------------------------------------------------------------------
# '실패' 상태는 즉시 편차로 취급 -- 실제 오케스트레이션 파이프라인(가짜 LLM)
# 끝까지 실행되는지 확인하는 통합 테스트.
# ------------------------------------------------------------------


def test_patch_status_failed_triggers_full_reevaluation_and_reverts_approved_status(db_session):
    incident = _create_and_simulate_incident("항만 파업", "실패편차재평가케이스")
    sop_id = _dispatch_one_sop_id(incident["id"])

    updated_incident = IncidentRepository(db_session).get(incident["id"])
    assert updated_incident.status == "승인"  # precondition: SOP dispatch requires this

    snapshot_count_before = len(OperationalSnapshotRepository(db_session).history_for_incident(incident["id"]))
    simulation_count_before = len(SimulationResultRepository(db_session).for_incident(incident["id"]))

    resp = client.patch(f"/sop/{sop_id}/status", json={"status": "실패", "actor": "운송담당자", "note": "차량 배차 실패"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "실패"
    assert body["deviation_check"] is not None
    assert body["deviation_check"]["reverted_to_in_progress"] is True
    assert body["deviation_check"]["final_status"] == "처리중"

    # incidents.status must have been reverted from '승인' (기존 승인 범위를
    # 벗어난 변경은 다시 담당자 승인을 받아야 한다, §6.3).
    db_session.expire_all()
    reverted_incident = IncidentRepository(db_session).get(incident["id"])
    assert reverted_incident.status == "처리중"

    # DAG + simulation actually re-ran (append-only new rows), through
    # orchestration.handle_execution_deviation -- not skipped/faked.
    assert (
        len(OperationalSnapshotRepository(db_session).history_for_incident(incident["id"]))
        == snapshot_count_before + 1
    )
    assert (
        len(SimulationResultRepository(db_session).for_incident(incident["id"]))
        > simulation_count_before
    )

    event_types = [
        row.event_type
        for row in AuditLogRepository(db_session).timeline_for_incident(incident["id"])
    ]
    assert "deviation_detected" in event_types
    assert "deviation_triggered_reevaluation" in event_types


# ------------------------------------------------------------------
# GET /incidents/{id}/timeline
# ------------------------------------------------------------------


def test_timeline_returns_chronological_events_with_deviation_flag(db_session):
    incident = _create_and_simulate_incident("항만 적체", "타임라인케이스")
    sop_id = _dispatch_one_sop_id(incident["id"])

    client.patch(f"/sop/{sop_id}/status", json={"status": "수신", "actor": "항만담당자"})
    client.patch(f"/sop/{sop_id}/status", json={"status": "실패", "actor": "항만담당자", "note": "슬롯 확보 실패"})

    resp = client.get(f"/incidents/{incident['id']}/timeline")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["incident_id"] == incident["id"]

    events = body["events"]
    # Chronological order.
    timestamps = [e["created_at"] for e in events]
    assert timestamps == sorted(timestamps)

    event_types = {e["event_type"] for e in events}
    assert "sop_dispatched" in event_types
    assert "sop_status_transition" in event_types
    assert "deviation_detected" in event_types
    assert "deviation_triggered_reevaluation" in event_types

    deviation_events = [e for e in events if e["is_deviation_event"]]
    assert {e["event_type"] for e in deviation_events} == {
        "deviation_detected",
        "deviation_triggered_reevaluation",
    }
    non_deviation_types = {"sop_dispatched", "sop_status_transition", "incident_approved"}
    for e in events:
        if e["event_type"] in non_deviation_types:
            assert e["is_deviation_event"] is False


def test_timeline_returns_404_for_unknown_incident():
    resp = client.get("/incidents/999999999/timeline")
    assert resp.status_code == 404
