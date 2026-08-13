"""Tests for the communication-sop agent (agents/communication-sop.md) --
app/services/communication.py + POST /approvals/{id}/dispatch-sop +
GET /incidents/{id}/sop-status.

Covers the DoD's minimum cases:
  1. 정상 발송 -- 5개 역할(항만/운송/공장/영업/계약) 각각 다른 핵심 정보가 채워짐,
     audit_log에 event_type='sop_dispatched' 행이 5개 기록됨.
  2. 승인 없이(decision_type이 승인/조건부승인이 아닌 경우) 발송 시도 시 거부(409).
  3. 자원확정(incidents.status='승인') 안 된 상태에서 발송 시도 시 거부(409) --
     decision_type='승인'인 approval이 있어도 incidents.status가 아직 '승인'으로
     전이되지 않았다면(오케스트레이션을 우회해 직접 만든 approval 등) 거부돼야
     한다.
  4. 멱등성 -- 같은 approval_id로 재호출해도 중복 발송하지 않고 기존 발송(같은
     sop_id들)을 그대로 반환한다.

Plus: GET /incidents/{id}/sop-status가 발송 이후 5개 sop_id 각각에 대해
수신/수락/완료가 아직 null인 트래커 항목을 반환하는지, 그리고 두 엔드포인트
모두 존재하지 않는 리소스에 404를 반환하는지.

Same LLM-faking pattern as tests/test_orchestration.py -- no real network
call anywhere in this file.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.approvals import ApprovalRepository
from app.repositories.audit_log import AuditLogRepository
from app.repositories.incidents import IncidentRepository

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


@pytest.fixture(autouse=True)
def _fake_llm_and_embeddings(monkeypatch):
    monkeypatch.setattr("app.rag.search.embed_text", lambda _text: [0.0] * 768)
    monkeypatch.setattr("app.services.response_design.get_llm_provider", lambda: _FakeCandidateProvider())
    monkeypatch.setattr("app.services.simulation.get_llm_provider", lambda: _FakeSimProvider())


def _loc(base: str) -> str:
    return f"{base} ({_RUN_ID}-{uuid.uuid4().hex[:6]})"


def _create_and_simulate_incident(type_: str, location: str) -> dict:
    """Same full pipeline setup as tests/test_orchestration.py --
    incident -> snapshot/DAG -> candidates -> validation -> simulation, so
    the resulting decision_package/response_candidates have real content
    for dispatch_sop's message context to read from."""

    unique_container = f"CTN-SOP-{uuid.uuid4().hex[:8]}"
    occurred_at = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "type": type_,
        "location": _loc(location),
        "occurred_at": occurred_at.isoformat(),
        "affected_targets": {
            "containers": [unique_container],
            "parts": ["PT-SOP-1"],
            "production_orders": ["PO-SOP-1"],
            "customers": ["Dealer-SOP-1"],
        },
    }
    resp = client.post("/incidents", json=payload)
    assert resp.status_code == 201, resp.text
    incident = resp.json()

    sim_resp = client.post(f"/incidents/{incident['id']}/simulate")
    assert sim_resp.status_code == 200, sim_resp.text

    # Mirrors the real approval flow (ARCHITECTURE.md §7.1 "담당자 승인" screen
    # reviews the decision package before approving) -- decision_packages is
    # only ever populated by this GET (response_optimization's build policy),
    # so without this call dispatch_sop would see no package/ranked
    # candidates/deadline at all, which is not the realistic precondition
    # these tests want to exercise.
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


# ------------------------------------------------------------------
# 1. 정상 발송 -- 5개 역할 각각 다른 핵심 정보, audit_log에 5행 기록
# ------------------------------------------------------------------


def test_dispatch_sop_sends_five_role_messages_with_distinct_content(db_session):
    incident = _create_and_simulate_incident("항만 적체", "정상발송케이스")
    approval = _approve(incident["id"])

    updated_incident = IncidentRepository(db_session).get(incident["id"])
    assert updated_incident.status == "승인"  # precondition sanity check

    resp = client.post(f"/approvals/{approval['id']}/dispatch-sop")
    assert resp.status_code == 200, resp.text
    results = resp.json()

    assert len(results) == 5
    roles = {r["role"] for r in results}
    assert roles == {"항만", "운송", "공장", "영업", "계약"}

    sop_ids = {r["sop_id"] for r in results}
    assert len(sop_ids) == 5  # each dispatch got its own audit_log id -> sop_id

    # audit_log actually has 5 new sop_dispatched rows for this incident.
    dispatched = AuditLogRepository(db_session).sop_dispatched_events_for_incident(incident["id"])
    assert len(dispatched) == 5
    assert {row.id for row in dispatched} == sop_ids

    # Each role's message carries genuinely different core info (not a
    # copy-pasted template) -- check the role-specific payload stored in
    # audit_log directly.
    by_role = {row.payload["role"]: row.payload["message"] for row in dispatched}

    assert "priority_release_containers" in by_role["항만"]["role_specific"]
    # container name must actually be present in the 항만 message.
    port_containers = by_role["항만"]["role_specific"]["priority_release_containers"]
    assert any("CTN-SOP-" in c for c in port_containers)

    assert "emergency_vehicle_dispatch_required" in by_role["운송"]["role_specific"]
    assert by_role["운송"]["role_specific"]["alternative_route_note"] != "미상"

    assert "production_sequence_change_proposal" in by_role["공장"]["role_specific"]
    assert by_role["공장"]["role_specific"]["related_parts"] == ["PT-SOP-1"]

    assert by_role["영업"]["role_specific"]["affected_customers"] == ["Dealer-SOP-1"]

    assert "ld_dnd_risk_note" in by_role["계약"]["role_specific"]

    # Common §6.2 fields present on every message, and non-empty.
    for role, message in by_role.items():
        for key in (
            "action",
            "completion_deadline",
            "reason",
            "related_containers",
            "related_parts",
            "related_production_orders",
            "referenced_documents",
            "expected_impact_if_not_executed",
            "approver",
            "scenario_version",
            "acknowledgment_method",
            "escalation_path",
            "message_text",
        ):
            assert key in message, f"{role} message missing common field {key}"
        assert message["approver"] == "김담당"
        assert message["message_text"]  # non-empty rendered text


def test_dispatch_sop_also_works_for_conditional_approval(db_session):
    incident = _create_and_simulate_incident("항만 파업", "조건부승인발송케이스")
    approval = _approve(
        incident["id"], decision_type="조건부승인", reason="대체 컨테이너 확보 완료 후 실행 개시 조건"
    )

    updated_incident = IncidentRepository(db_session).get(incident["id"])
    assert updated_incident.status == "승인"

    resp = client.post(f"/approvals/{approval['id']}/dispatch-sop")
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 5


# ------------------------------------------------------------------
# 2. 승인/조건부승인이 아닌 경우 발송 거부 (409)
# ------------------------------------------------------------------


def test_dispatch_sop_rejected_when_not_approved(db_session):
    incident = _create_and_simulate_incident("항만 파업", "미승인발송거부케이스")
    approval = _approve(incident["id"], decision_type="반려", reason="예산 초과로 반려")

    updated_incident = IncidentRepository(db_session).get(incident["id"])
    assert updated_incident.status == "처리중"  # 반려는 승인 상태로 전이하지 않음

    resp = client.post(f"/approvals/{approval['id']}/dispatch-sop")
    assert resp.status_code == 409, resp.text

    # No audit_log dispatch rows must have been created.
    dispatched = AuditLogRepository(db_session).sop_dispatched_events_for_incident(incident["id"])
    assert dispatched == []


# ------------------------------------------------------------------
# 3. 자원확정(incidents.status='승인') 안 된 상태에서 발송 거부 (409)
# ------------------------------------------------------------------


def test_dispatch_sop_rejected_when_resource_not_confirmed(db_session):
    """decision_type='승인'인 approval이 존재해도, incidents.status가 아직
    '승인'으로 전이되지 않았다면(오케스트레이션을 우회한 approval 등) SOP를
    발송하면 안 된다. 실제로 이 상태를 재현하려면 오케스트레이션의
    process_approval을 거치지 않고 ApprovalRepository로 직접 승인 행만
    만든다 -- incidents.status는 '유효'로 남아 있다."""

    incident = _create_and_simulate_incident("항만 적체", "자원확정미완료케이스")

    updated_incident = IncidentRepository(db_session).get(incident["id"])
    assert updated_incident.status == "유효"  # simulate만 했지 승인 전이는 없었음

    approval = ApprovalRepository(db_session).add(
        incident_id=incident["id"],
        decision_type="승인",
        reason="오케스트레이션을 우회해 직접 만든 승인(자원확정 신호 없음)",
        approver="tester",
    )

    resp = client.post(f"/approvals/{approval.id}/dispatch-sop")
    assert resp.status_code == 409, resp.text

    dispatched = AuditLogRepository(db_session).sop_dispatched_events_for_incident(incident["id"])
    assert dispatched == []


def test_dispatch_sop_returns_404_for_unknown_approval():
    resp = client.post("/approvals/999999999/dispatch-sop")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# 4. 멱등성 -- 같은 approval_id로 재호출해도 중복 발송하지 않음
# ------------------------------------------------------------------


def test_dispatch_sop_is_idempotent_for_same_approval(db_session):
    incident = _create_and_simulate_incident("항만 적체", "멱등성케이스")
    approval = _approve(incident["id"])

    first = client.post(f"/approvals/{approval['id']}/dispatch-sop")
    assert first.status_code == 200, first.text
    first_sop_ids = sorted(r["sop_id"] for r in first.json())

    second = client.post(f"/approvals/{approval['id']}/dispatch-sop")
    assert second.status_code == 200, second.text
    second_sop_ids = sorted(r["sop_id"] for r in second.json())

    assert first_sop_ids == second_sop_ids

    dispatched = AuditLogRepository(db_session).sop_dispatched_events_for_incident(incident["id"])
    assert len(dispatched) == 5  # still just 5, not 10


# ------------------------------------------------------------------
# GET /incidents/{id}/sop-status
# ------------------------------------------------------------------


def test_sop_status_lists_dispatched_entries_with_null_followup_state():
    incident = _create_and_simulate_incident("항만 적체", "SOP상태조회케이스")
    approval = _approve(incident["id"])

    dispatch_resp = client.post(f"/approvals/{approval['id']}/dispatch-sop")
    assert dispatch_resp.status_code == 200, dispatch_resp.text
    dispatched_sop_ids = {r["sop_id"] for r in dispatch_resp.json()}

    status_resp = client.get(f"/incidents/{incident['id']}/sop-status")
    assert status_resp.status_code == 200, status_resp.text
    body = status_resp.json()
    assert body["incident_id"] == incident["id"]

    statuses = body["sop_statuses"]
    assert {s["sop_id"] for s in statuses} == dispatched_sop_ids
    assert {s["role"] for s in statuses} == {"항만", "운송", "공장", "영업", "계약"}

    for s in statuses:
        assert s["status"] == "발송"
        assert s["received_at"] is None
        assert s["accepted_at"] is None
        assert s["completed_at"] is None
        assert s["failed_at"] is None
        assert s["events"] == []  # execution-tracking이 아직 없으므로 항상 빈 리스트


def test_sop_status_empty_before_any_dispatch():
    incident = _create_and_simulate_incident("항만 적체", "발송전상태조회케이스")

    resp = client.get(f"/incidents/{incident['id']}/sop-status")
    assert resp.status_code == 200, resp.text
    assert resp.json()["sop_statuses"] == []


def test_sop_status_returns_404_for_unknown_incident():
    resp = client.get("/incidents/999999999/sop-status")
    assert resp.status_code == 404
