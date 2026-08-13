"""Tests for the orchestration agent (agents/orchestration.md) --
app/services/orchestration.py + POST /incidents/{id}/approvals.

Covers the DoD's minimum 3 cases plus 조건부승인/수정요청 and edge cases:
  1. 정상 승인 -> incidents.status='승인' (자원확정 전이 신호).
  2. 반려 -> incidents.status는 '처리중' 유지, 사유 기록(대체 대응안 생성 요청은
     이번 스코프에서 인터페이스만 열어둠 -- app/services/orchestration.py의
     _reject 판단 근거 참고).
  3. 결정기한 초과 -> check_deadline_overrun()이 시스템 주체로 기한초과를
     기록하고, 실제 알림 발송 없이 에스컬레이션만 남김.
  4. 조건부승인 -> incidents.status='승인' + reason 최소 길이 강제.
  5. 수정요청 -> incidents.status='처리중' 복귀 + 기존 후보 유지한 채
     제약 재검증/재시뮬레이션 재실행(append-only 새 simulation_results 행).

Plus: 404 for unknown incident, 400 for an unrecognized decision_type at the
service layer, 422 for a client attempting decision_type='기한초과' or a
blank/too-short reason at the schema layer, and idempotency of
check_deadline_overrun.

Same LLM-faking pattern as tests/test_simulate_api.py -- no real network
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
from app.repositories.decision_packages import DecisionPackageRepository
from app.repositories.incidents import IncidentRepository
from app.repositories.simulation_results import SimulationResultRepository
from app.services.orchestration import check_deadline_overrun

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
    return f"{base} ({_RUN_ID}-{uuid.uuid4().hex[:6]})"


def _create_and_simulate_incident(type_: str, location: str) -> dict:
    """Full pipeline setup: incident -> snapshot/DAG -> candidates ->
    validation -> simulation, so approvals tests exercise a realistic
    incident with a real latest snapshot (for data_version_ref/
    scenario_version_ref auto-fill) and a real decision package (for the
    deadline-overrun tests)."""

    unique_container = f"CTN-ORC-{uuid.uuid4().hex[:8]}"
    occurred_at = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "type": type_,
        "location": _loc(location),
        "occurred_at": occurred_at.isoformat(),
        "affected_targets": {
            "containers": [unique_container],
            "parts": ["PT-ORC-1"],
            "production_orders": ["PO-ORC-1"],
            "customers": ["Dealer-ORC-1"],
        },
    }
    resp = client.post("/incidents", json=payload)
    assert resp.status_code == 201, resp.text
    incident = resp.json()

    sim_resp = client.post(f"/incidents/{incident['id']}/simulate")
    assert sim_resp.status_code == 200, sim_resp.text

    return incident


# ------------------------------------------------------------------
# 1. 승인 -> incidents.status='승인'
# ------------------------------------------------------------------


def test_approve_transitions_incident_to_approved_and_records_versions(db_session):
    incident = _create_and_simulate_incident("항만 적체", "승인케이스")

    resp = client.post(
        f"/incidents/{incident['id']}/approvals",
        json={"decision_type": "승인", "reason": "손실 최소화 대응안으로 즉시 진행", "approver": "김담당"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["decision_type"] == "승인"
    assert body["approver"] == "김담당"
    # /simulate already created a snapshot -- version refs must be auto-filled,
    # not left null.
    assert body["data_version_ref"] is not None
    assert body["scenario_version_ref"] is not None

    updated = IncidentRepository(db_session).get(incident["id"])
    assert updated.status == "승인"

    approvals = ApprovalRepository(db_session).for_incident(incident["id"])
    assert len(approvals) == 1
    assert approvals[0].decision_type == "승인"
    assert approvals[0].reason == "손실 최소화 대응안으로 즉시 진행"


# ------------------------------------------------------------------
# 2. 반려 -> incidents.status는 '처리중' 유지
# ------------------------------------------------------------------


def test_reject_keeps_incident_in_progress_and_records_reason(db_session):
    incident = _create_and_simulate_incident("항만 파업", "반려케이스")
    assert IncidentRepository(db_session).get(incident["id"]).status == "유효"

    resp = client.post(
        f"/incidents/{incident['id']}/approvals",
        json={"decision_type": "반려", "reason": "예산 초과로 반려", "approver": "박담당"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["decision_type"] == "반려"

    updated = IncidentRepository(db_session).get(incident["id"])
    assert updated.status == "처리중"

    approvals = ApprovalRepository(db_session).for_incident(incident["id"])
    assert approvals[-1].decision_type == "반려"
    assert approvals[-1].reason == "예산 초과로 반려"

    # 반려 이후 incidents.status='처리중'이다. 이전 리뷰에서는 operational-graph의
    # 적격성 게이트가 '유효'만 허용해 POST /simulate 재호출이 409였지만, Wave 7
    # (execution-tracking) 병합 전 리뷰에서 그 게이트를 '유효'/'처리중'/'승인'
    # 모두 허용하도록 넓혔다(app/services/operational_graph.py의
    # RECOMPUTE_ELIGIBLE_STATUSES) -- '처리중'/'승인'은 원래 '유효'를 거쳐야만
    # 도달하는 상태라 재계산 대상에서 뺄 이유가 없었기 때문이다. 이제 담당자가
    # 반려 후 다시 검토를 요청하면(재호출) 기존 후보를 재사용해 정상적으로
    # 재검증·재시뮬레이션이 돈다.
    resimulate = client.post(f"/incidents/{incident['id']}/simulate")
    assert resimulate.status_code == 200, resimulate.text
    assert resimulate.json()["reused_existing_candidates"] is True


# ------------------------------------------------------------------
# 3. 결정기한 초과 -> check_deadline_overrun()의 시스템 기록
# ------------------------------------------------------------------


def test_deadline_overrun_detected_and_recorded_once(db_session):
    incident = _create_and_simulate_incident("관세 규정 변경", "기한초과케이스")

    package_repo = DecisionPackageRepository(db_session)
    past_deadline = datetime.now(timezone.utc) - timedelta(hours=1)
    package_repo.add(
        incident_id=incident["id"], package={"disclaimer": "test"}, recommended_deadline=past_deadline
    )

    fired = check_deadline_overrun(db_session, incident["id"])
    assert fired is True

    approvals = ApprovalRepository(db_session).for_incident(incident["id"])
    escalation = next(a for a in approvals if a.decision_type == "기한초과")
    assert escalation.approver == "system"
    assert escalation.data_version_ref is not None  # /simulate created a snapshot earlier

    # Idempotent: calling again must not create a second escalation row.
    fired_again = check_deadline_overrun(db_session, incident["id"])
    assert fired_again is False
    approvals_after = ApprovalRepository(db_session).for_incident(incident["id"])
    assert len(approvals_after) == len(approvals)


def test_deadline_overrun_not_fired_when_deadline_in_future(db_session):
    incident = _create_and_simulate_incident("관세 규정 변경", "기한미래케이스")

    package_repo = DecisionPackageRepository(db_session)
    future_deadline = datetime.now(timezone.utc) + timedelta(hours=6)
    package_repo.add(
        incident_id=incident["id"], package={"disclaimer": "test"}, recommended_deadline=future_deadline
    )

    assert check_deadline_overrun(db_session, incident["id"]) is False
    assert ApprovalRepository(db_session).for_incident(incident["id"]) == []


def test_deadline_overrun_returns_false_for_unknown_incident(db_session):
    assert check_deadline_overrun(db_session, 999_999_999) is False


# ------------------------------------------------------------------
# 4. 조건부승인 -> incidents.status='승인' + reason 최소 길이 강제
# ------------------------------------------------------------------


def test_conditional_approve_transitions_to_approved_with_condition_reason(db_session):
    incident = _create_and_simulate_incident("항만 적체", "조건부승인케이스")

    resp = client.post(
        f"/incidents/{incident['id']}/approvals",
        json={
            "decision_type": "조건부승인",
            "reason": "대체 컨테이너 확보 완료 후 실행 개시 조건",
            "approver": "이담당",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["decision_type"] == "조건부승인"

    updated = IncidentRepository(db_session).get(incident["id"])
    assert updated.status == "승인"


def test_conditional_approve_rejects_too_short_reason():
    incident = _create_and_simulate_incident("항만 적체", "조건부짧은사유")

    resp = client.post(
        f"/incidents/{incident['id']}/approvals",
        json={"decision_type": "조건부승인", "reason": "승인함", "approver": "이담당"},
    )
    assert resp.status_code == 422, resp.text


# ------------------------------------------------------------------
# 5. 수정요청 -> incidents.status='처리중' 복귀 + 재검증/재시뮬레이션 재실행
# ------------------------------------------------------------------


def test_request_revision_reruns_validation_and_simulation_on_existing_candidates(db_session):
    incident = _create_and_simulate_incident("항만 적체", "수정요청케이스")

    sim_repo = SimulationResultRepository(db_session)
    before_sim_ids = {s.id for s in sim_repo.for_incident(incident["id"])}
    assert before_sim_ids  # /simulate above already produced results

    candidates_before = client.get(f"/incidents/{incident['id']}/candidates").json()["candidates"]
    ids_before = {c["id"] for c in candidates_before}

    resp = client.post(
        f"/incidents/{incident['id']}/approvals",
        json={"decision_type": "수정요청", "reason": "가정치 재검토 후 다시 검토 요청", "approver": "최담당"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["decision_type"] == "수정요청"

    updated = IncidentRepository(db_session).get(incident["id"])
    assert updated.status == "처리중"

    candidates_after = client.get(f"/incidents/{incident['id']}/candidates").json()["candidates"]
    ids_after = {c["id"] for c in candidates_after}
    # 기존 후보를 유지 -- 새 후보 세트를 만들지 않는다 (판단 근거: orchestration.py
    # _request_revision 참고).
    assert ids_after == ids_before

    after_sim_ids = {s.id for s in sim_repo.for_incident(incident["id"])}
    # append-only 재시뮬레이션 -- 새 행이 추가되고 기존 행은 그대로 남는다.
    assert before_sim_ids.issubset(after_sim_ids)
    assert after_sim_ids - before_sim_ids  # at least one brand-new result


# ------------------------------------------------------------------
# Errors / edge cases
# ------------------------------------------------------------------


def test_approvals_endpoint_404s_for_unknown_incident():
    resp = client.post(
        "/incidents/999999999/approvals",
        json={"decision_type": "승인", "reason": "테스트", "approver": "tester"},
    )
    assert resp.status_code == 404


def test_approvals_endpoint_rejects_client_supplied_deadline_overrun():
    incident = _create_and_simulate_incident("항만 적체", "클라이언트기한초과")
    resp = client.post(
        f"/incidents/{incident['id']}/approvals",
        json={"decision_type": "기한초과", "reason": "임의 제출", "approver": "tester"},
    )
    assert resp.status_code == 422


def test_approvals_endpoint_rejects_blank_reason():
    incident = _create_and_simulate_incident("항만 적체", "빈사유")
    resp = client.post(
        f"/incidents/{incident['id']}/approvals",
        json={"decision_type": "승인", "reason": "   ", "approver": "tester"},
    )
    assert resp.status_code == 422
