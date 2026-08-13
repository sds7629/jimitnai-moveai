"""Tests for the post-report agent (agents/post-report.md) --
app/services/post_report.py + app/services/cost_attribution.py +
GET /incidents/{id}/post-report + GET /incidents/{id}/cost-attribution.

Covers the DoD's minimum 3 cases:
  1. 정상 종료 사건의 확정 보고서 생성 -- 12개 섹션 모두 채워짐,
     report_status='잠정'.
  2. baseline 레코드가 없는 예외 상황 -- 예외를 던지지 않고 구조화된
     "available: False" 값으로 처리.
  3. (test_roi.py에서) ROI가 3개 시나리오로 표시됨.

Plus: 비용 귀속 분류(LD/D&D 조항 유무에 따른 3가지 휴리스틱 분기), 알 수 없는
incident_id에 대한 404/IncidentNotFoundError, report_status가 사건 상태와
무관하게 항상 '잠정'인지, 실행 편차/SOP 이력이 실제로 섹션에 반영되는지.

이 웨이브는 LLM 호출이 전혀 없는 순수 집계 웨이브라, response-optimization/
simulation 웨이브 테스트들과 달리 전체 LLM 파이프라인을 거치지 않고 리포지토리
레이어로 직접 fixture를 구성한다 (incident -> snapshot -> candidates ->
simulation_results -> decision_package -> approval -> audit_log). RAG 임베딩
호출만 fake embed_fn으로 모킹한다 (test_knowledge_retrieval.py와 동일한 패턴).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.llm.gemini_embeddings import EMBEDDING_DIM
from app.main import app
from app.repositories.approvals import ApprovalRepository
from app.repositories.audit_log import AuditLogRepository
from app.repositories.decision_packages import DecisionPackageRepository
from app.repositories.incidents import IncidentRepository
from app.repositories.operational_snapshots import OperationalSnapshotRepository
from app.repositories.response_candidates import ResponseCandidateRepository
from app.repositories.simulation_results import SimulationResultRepository
from app.services.cost_attribution import (
    CUSTOMER_AVOIDANCE_KEY,
    DIRECT_PL_KEY,
    DISPUTE_NEGOTIABLE_KEY,
    classify_cost_attribution,
)
from app.services.cost_attribution import IncidentNotFoundError as CostAttrIncidentNotFoundError
from app.services.post_report import (
    ACTUAL_STATUS_UNCONFIRMED,
    REPORT_STATUS_PROVISIONAL,
    build_post_report,
)
from app.services.post_report import IncidentNotFoundError as PostReportIncidentNotFoundError

client = TestClient(app)
_RUN_ID = uuid.uuid4().hex[:8]
_RUN_OFFSET = int(_RUN_ID, 16) % (EMBEDDING_DIM - 10)

REQUIRED_SECTION_KEYS = [
    "1_사건_개요와_발생시점",
    "2_최초_예상과_실제_진행_과정",
    "3_주요_동적_변수의_변화",
    "4_검토한_대응안과_제외_사유",
    "5_최종_결정과_승인자",
    "6_SOP_발송_수신_수락_실행_이력",
    "7_예상_손실과_실제_손실",
    "8_회피한_손실과_추가_발생_비용",
    "9_LD_DND_귀책_및_비용_부담_주체",
    "10_시뮬레이션_오차와_가정의_영향",
    "11_자원_확보_실패_실행_편차와_에스컬레이션_이력",
    "12_향후_SOP_모델_데이터_개선사항",
]


def _one_hot(index: int) -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    vec[index % EMBEDDING_DIM] = 1.0
    return vec


def _no_op_embed(_text: str) -> list[float]:
    # No contract documents match this -- used whenever a test doesn't care
    # about RAG matching and just needs search_similar_chunks not to hit the
    # real (unavailable in this dev env) Gemini API.
    return _one_hot(_RUN_OFFSET)


@pytest.fixture(autouse=True)
def _fake_embeddings(monkeypatch):
    """build_post_report -> classify_cost_attribution calls
    search_similar_chunks without an explicit embed_fn (production default:
    real Gemini). No GEMINI_API_KEY exists in this dev/test environment, so
    every test in this module needs the module-level embed_text monkeypatched
    -- same pattern as tests/test_response_optimization.py's
    `_fake_llm_and_embeddings` fixture."""

    monkeypatch.setattr("app.rag.search.embed_text", _no_op_embed)


def _loc(base: str) -> str:
    return f"{base} ({_RUN_ID})"


def _make_incident(db_session, *, type_="항만 적체", status="유효"):
    incident = IncidentRepository(db_session).add(
        type=type_,
        location=_loc("부산항 3부두"),
        occurred_at=datetime.now(timezone.utc) - timedelta(hours=6),
        status=status,
        affected_targets={"containers": ["CTN-PR-1"], "parts": ["PT-PR-1"]},
        assumptions=["초기 가정: 재고 3일치"],
    )
    return incident


def _make_snapshot(db_session, incident_id, *, data_version, scenario_version, quality_mode="normal", assumptions=None):
    return OperationalSnapshotRepository(db_session).add(
        incident_id=incident_id,
        data_version=data_version,
        scenario_version=scenario_version,
        assumptions=assumptions or [],
        operational_state={"inventory_days": 3},
        quality_mode=quality_mode,
        freshness_seconds=120,
        coverage_ratio=0.9,
    )


def _make_candidate(db_session, incident_id, snapshot_id, *, candidate_type, description, validation_status="가능", **kw):
    return ResponseCandidateRepository(db_session).add(
        incident_id=incident_id,
        snapshot_id=snapshot_id,
        candidate_type=candidate_type,
        description=description,
        reference_document_ids=[],
        preconditions=kw.pop("preconditions", []),
        start_time_variant=kw.pop("start_time_variant", None),
        validation_status=validation_status,
        exclusion_category=kw.pop("exclusion_category", None),
        exclusion_detail=kw.pop("exclusion_detail", None),
    )


def _make_sim(db_session, incident_id, candidate_id, *, expected_loss, p90=None, cvar=None, confidence=0.7, data_version="v1", scenario_version="v1"):
    return SimulationResultRepository(db_session).add(
        candidate_id=candidate_id,
        incident_id=incident_id,
        expected_loss=expected_loss,
        p90=p90 or expected_loss * 2,
        cvar=cvar or expected_loss * 2.5,
        sensitivity_variables=["안전재고 소진 속도"],
        confidence=confidence,
        fact={"qty": 100},
        inference={"depletion_hours": 10},
        assumption={"consumption_rate": "steady"},
        data_version=data_version,
        scenario_version=scenario_version,
    )


def _make_full_scenario(db_session):
    """baseline + 승인 후보 + 제외된 후보 + decision_package + approval +
    SOP 발송/상태이력 + 편차 이벤트까지 전부 갖춘 정상 케이스."""

    incident = _make_incident(db_session)

    snap1 = _make_snapshot(
        db_session, incident.id, data_version="v1", scenario_version="v1",
        quality_mode="normal", assumptions=["재고 3일치"],
    )
    snap2 = _make_snapshot(
        db_session, incident.id, data_version="v2", scenario_version="v1",
        quality_mode="limited", assumptions=["재고 3일치", "항만 서류 지연 가정 추가"],
    )

    baseline = _make_candidate(
        db_session, incident.id, snap1.id,
        candidate_type="baseline", description="무대응", start_time_variant="즉시",
        validation_status="가능",
    )
    approved = _make_candidate(
        db_session, incident.id, snap2.id,
        candidate_type="단일", description="컨테이너 우선 반출", start_time_variant="now",
        validation_status="가능",
    )
    excluded = _make_candidate(
        db_session, incident.id, snap2.id,
        candidate_type="단일", description="대체 항만 우회", start_time_variant="+6h",
        validation_status="불가능", exclusion_category="자원부족", exclusion_detail="대체 항만 슬롯 없음",
    )

    baseline_sim = _make_sim(db_session, incident.id, baseline.id, expected_loss=10_000_000)
    approved_sim = _make_sim(db_session, incident.id, approved.id, expected_loss=3_000_000)

    DecisionPackageRepository(db_session).add(
        incident_id=incident.id,
        package={
            "ranked_candidates": {
                "ranked": [
                    {"candidate_id": approved.id, "candidate_type": "단일", "rank": 1},
                    {"candidate_id": baseline.id, "candidate_type": "baseline", "rank": 2},
                ],
                "excluded_from_ranking": [],
            }
        },
        recommended_deadline=datetime.now(timezone.utc) + timedelta(hours=6),
    )

    approval = ApprovalRepository(db_session).add(
        incident_id=incident.id,
        decision_type="승인",
        reason="컨테이너 우선 반출 승인",
        approver="담당자A",
        data_version_ref="v2",
        scenario_version_ref="v1",
    )

    audit_repo = AuditLogRepository(db_session)
    dispatch_row = audit_repo.add(
        incident_id=incident.id,
        event_type="sop_dispatched",
        actor="communication-sop-service",
        reason="SOP 발송 -- 항만 담당자",
        payload={"approval_id": approval.id, "role": "항만", "message": {"action": "우선 반출", "message_text": "..."}},
    )
    audit_repo.add(
        incident_id=incident.id,
        event_type="sop_status_transition",
        actor="항만담당자",
        reason=None,
        payload={"sop_id": dispatch_row.id, "status": "수신", "note": None},
    )
    audit_repo.add(
        incident_id=incident.id,
        event_type="sop_status_transition",
        actor="항만담당자",
        reason=None,
        payload={"sop_id": dispatch_row.id, "status": "완료", "note": "반출 완료"},
    )
    audit_repo.add(
        incident_id=incident.id,
        event_type="deviation_detected",
        actor="execution-tracking-service",
        reason="기한 내 미수락 -- 결정기한 경과",
        payload={"related_sop_ids": [dispatch_row.id], "detail": {}},
    )

    return {
        "incident": incident,
        "baseline": baseline,
        "approved": approved,
        "excluded": excluded,
        "baseline_sim": baseline_sim,
        "approved_sim": approved_sim,
    }


# ============================================================
# DoD case 1: 정상 종료 사건의 확정 보고서 생성
# ============================================================
def test_build_post_report_normal_case_all_12_sections_filled(db_session):
    ctx = _make_full_scenario(db_session)
    incident_id = ctx["incident"].id

    report = build_post_report(db_session, incident_id)

    assert report["incident_id"] == incident_id
    assert report["report_status"] == REPORT_STATUS_PROVISIONAL
    assert report["actual_status"] == ACTUAL_STATUS_UNCONFIRMED
    assert set(report["sections"].keys()) == set(REQUIRED_SECTION_KEYS)
    for key in REQUIRED_SECTION_KEYS:
        assert report["sections"][key] is not None

    s1 = report["sections"]["1_사건_개요와_발생시점"]
    assert s1["incident_id"] == incident_id
    assert s1["type"] == "항만 적체"

    s2 = report["sections"]["2_최초_예상과_실제_진행_과정"]
    assert s2["expected"]["baseline"]["available"] is True
    assert s2["expected"]["approved_candidate"]["available"] is True
    assert s2["actual_status"] == "미확정"
    assert s2["actual_progress"]["available"] is False

    s3 = report["sections"]["3_주요_동적_변수의_변화"]
    assert s3["snapshot_count"] == 2
    assert isinstance(s3["changes_summary"], list) and len(s3["changes_summary"]) == 1
    assert "quality_mode" in s3["changes_summary"][0]["summary"]

    s4 = report["sections"]["4_검토한_대응안과_제외_사유"]
    assert s4["total_count"] == 3
    assert s4["excluded_count"] == 1

    s5 = report["sections"]["5_최종_결정과_승인자"]
    assert s5["final_decision"]["available"] is True
    assert s5["final_decision"]["decision_type"] == "승인"
    assert s5["final_decision"]["approver"] == "담당자A"

    s6 = report["sections"]["6_SOP_발송_수신_수락_실행_이력"]
    assert s6["sop_count"] == 1
    assert s6["dispatches"][0]["status"] == "완료"

    s7 = report["sections"]["7_예상_손실과_실제_손실"]
    assert s7["actual_status"] == "미확정"
    assert s7["actual_loss"]["available"] is False

    s8 = report["sections"]["8_회피한_손실과_추가_발생_비용"]
    assert s8["expected_avoided_loss"]["available"] is True
    assert s8["expected_avoided_loss"]["amount"] == pytest.approx(10_000_000 - 3_000_000)
    assert s8["additional_cost_incurred"]["available"] is False

    s9 = report["sections"]["9_LD_DND_귀책_및_비용_부담_주체"]
    assert s9["is_heuristic"] is True
    assert set(s9["breakdown"].keys()) == {DIRECT_PL_KEY, CUSTOMER_AVOIDANCE_KEY, DISPUTE_NEGOTIABLE_KEY}

    s10 = report["sections"]["10_시뮬레이션_오차와_가정의_영향"]
    assert s10["error_calculable"] is False
    assert len(s10["candidates"]) == 2  # baseline + approved (excluded has no sim)

    s11 = report["sections"]["11_자원_확보_실패_실행_편차와_에스컬레이션_이력"]
    assert s11["deviation_event_count"] == 1

    s12 = report["sections"]["12_향후_SOP_모델_데이터_개선사항"]
    assert isinstance(s12, list) and len(s12) >= 3
    assert all(isinstance(item, dict) and "category" in item and "description" in item for item in s12)


def test_get_post_report_api_matches_service(db_session, monkeypatch):
    monkeypatch.setattr("app.rag.search.embed_text", _no_op_embed)
    ctx = _make_full_scenario(db_session)
    incident_id = ctx["incident"].id

    resp = client.get(f"/incidents/{incident_id}/post-report")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["report_status"] == "잠정"
    assert set(body["sections"].keys()) == set(REQUIRED_SECTION_KEYS)


# ============================================================
# DoD case 2: baseline 레코드가 없는 예외 상황
# ============================================================
def test_build_post_report_no_baseline_candidate_reports_unavailable_not_error(db_session):
    incident = _make_incident(db_session)
    # 후보를 전혀 만들지 않는다 -- baseline_for_incident가 None을 반환해야 함.

    report = build_post_report(db_session, incident.id)

    assert report["report_status"] == REPORT_STATUS_PROVISIONAL
    assert set(report["sections"].keys()) == set(REQUIRED_SECTION_KEYS)

    s2 = report["sections"]["2_최초_예상과_실제_진행_과정"]
    assert s2["expected"]["baseline"]["available"] is False

    s8 = report["sections"]["8_회피한_손실과_추가_발생_비용"]
    assert s8["expected_avoided_loss"]["available"] is False
    assert "baseline" in s8["expected_avoided_loss"]["reason"]

    s4 = report["sections"]["4_검토한_대응안과_제외_사유"]
    assert s4["total_count"] == 0

    s5 = report["sections"]["5_최종_결정과_승인자"]
    assert s5["final_decision"]["available"] is False

    s6 = report["sections"]["6_SOP_발송_수신_수락_실행_이력"]
    assert s6["sop_count"] == 0

    s12 = report["sections"]["12_향후_SOP_모델_데이터_개선사항"]
    # baseline 외 대응안이 0개이므로 "대응안 다양성 부족" 개선 항목이 있어야 함
    assert any("대응안" in item["category"] for item in s12)


def test_build_post_report_report_status_always_provisional_regardless_of_incident_status(db_session):
    ctx = _make_full_scenario(db_session)
    incident_id = ctx["incident"].id
    IncidentRepository(db_session).update(incident_id, status="종료")

    report = build_post_report(db_session, incident_id)
    assert report["report_status"] == "잠정"
    assert report["sections"]["1_사건_개요와_발생시점"]["status"] == "종료"


# ============================================================
# 알 수 없는 incident_id
# ============================================================
def test_build_post_report_unknown_incident_raises(db_session):
    with pytest.raises(PostReportIncidentNotFoundError):
        build_post_report(db_session, 999_999_999)


def test_get_post_report_api_404_for_unknown_incident():
    resp = client.get("/incidents/999999999/post-report")
    assert resp.status_code == 404


def test_get_cost_attribution_api_404_for_unknown_incident():
    resp = client.get("/incidents/999999999/cost-attribution")
    assert resp.status_code == 404


# ============================================================
# 비용 귀속 분류
#
# search_similar_chunks의 실제 pgvector top-k 검색은 유사도 최소 기준 없이
# "가장 가까운 K개"를 그대로 반환한다(test_knowledge_retrieval.py에서 이미
# 검증됨) -- documents/document_chunks는 append-only라 이전 테스트 실행에서
# 남긴 계약 조항 청크가 계속 쌓이므로, DB에 실제로 아무것도 넣지 않고 "검색
# 결과가 비었다"를 기대하는 테스트는 신선하지 않은 볼륨에서 반복 실행할 때
# 이전 실행의 잔여 데이터 때문에 깨질 수 있다(작업 브리핑이 경고한 "누적
# 데이터로 인한 순서의존 플레이키니스"). 그래서 여기서는 classify_cost_
# attribution이 import한 search_similar_chunks 자체를 모킹해 분류 로직만
# 격리해서 검증한다 -- RAG 검색 자체의 정확성은 test_knowledge_retrieval.py의
# 책임이다.
# ============================================================
def test_classify_cost_attribution_no_clauses_found_defaults_to_dispute(db_session, monkeypatch):
    monkeypatch.setattr("app.services.cost_attribution.search_similar_chunks", lambda *a, **kw: [])
    ctx = _make_full_scenario(db_session)
    incident_id = ctx["incident"].id

    result = classify_cost_attribution(db_session, incident_id)

    assert result["is_heuristic"] is True
    assert result["matched_ld_clauses"] == []
    assert result["matched_dnd_clauses"] == []
    breakdown = result["breakdown"]
    assert breakdown[DIRECT_PL_KEY] == 0.0
    assert breakdown[CUSTOMER_AVOIDANCE_KEY] == 0.0
    assert breakdown[DISPUTE_NEGOTIABLE_KEY] == pytest.approx(10_000_000 - 3_000_000)


def _fake_chunk(chunk_text: str, *, chunk_id=1, document_id=1) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "doc_type": "계약",
        "title": f"테스트 계약서 ({_RUN_ID})",
        "source": "test-fixture",
        "chunk_type": "조항",
        "chunk_text": chunk_text,
        "metadata": {},
    }


def test_classify_cost_attribution_dnd_clause_classifies_as_customer_avoidance(db_session, monkeypatch):
    fake_chunks = [_fake_chunk("체선료 및 체화료(D&D)는 화주가 부담한다")]
    monkeypatch.setattr("app.services.cost_attribution.search_similar_chunks", lambda *a, **kw: fake_chunks)

    ctx = _make_full_scenario(db_session)
    incident_id = ctx["incident"].id

    result = classify_cost_attribution(db_session, incident_id)

    assert len(result["matched_dnd_clauses"]) >= 1
    assert result["matched_ld_clauses"] == []
    breakdown = result["breakdown"]
    assert breakdown[DIRECT_PL_KEY] == 0.0
    assert breakdown[CUSTOMER_AVOIDANCE_KEY] == pytest.approx(10_000_000 - 3_000_000)
    assert breakdown[DISPUTE_NEGOTIABLE_KEY] == 0.0


def test_classify_cost_attribution_ld_clause_stays_dispute_not_direct_pl(db_session, monkeypatch):
    """LD 조항이 발견돼도 귀책 주체를 판단할 근거가 없으므로 '직접손익'으로
    단정하지 않고 분쟁·협상 가능 금액으로 남아야 한다 (작업 브리핑의 명시적
    요구사항)."""

    fake_chunks = [_fake_chunk("제5조(지연배상금) 지연배상금(LD)은 귀책 주체가 부담한다")]
    monkeypatch.setattr("app.services.cost_attribution.search_similar_chunks", lambda *a, **kw: fake_chunks)

    ctx = _make_full_scenario(db_session)
    incident_id = ctx["incident"].id

    result = classify_cost_attribution(db_session, incident_id)

    assert len(result["matched_ld_clauses"]) >= 1
    breakdown = result["breakdown"]
    assert breakdown[DIRECT_PL_KEY] == 0.0
    assert breakdown[CUSTOMER_AVOIDANCE_KEY] == 0.0
    assert breakdown[DISPUTE_NEGOTIABLE_KEY] == pytest.approx(10_000_000 - 3_000_000)


def test_classify_cost_attribution_amount_unavailable_when_no_baseline(db_session):
    incident = _make_incident(db_session)
    result = classify_cost_attribution(db_session, incident.id, embed_fn=_no_op_embed)

    assert result["avoided_loss_basis"]["available"] is False
    breakdown = result["breakdown"]
    assert breakdown[DIRECT_PL_KEY] is None
    assert breakdown[CUSTOMER_AVOIDANCE_KEY] is None
    assert breakdown[DISPUTE_NEGOTIABLE_KEY] is None


def test_classify_cost_attribution_unknown_incident_raises(db_session):
    with pytest.raises(CostAttrIncidentNotFoundError):
        classify_cost_attribution(db_session, 999_999_999, embed_fn=_no_op_embed)


def test_get_cost_attribution_api_matches_service(db_session, monkeypatch):
    monkeypatch.setattr("app.rag.search.embed_text", _no_op_embed)
    ctx = _make_full_scenario(db_session)
    incident_id = ctx["incident"].id

    resp = client.get(f"/incidents/{incident_id}/cost-attribution")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_heuristic"] is True
    assert body["breakdown"][DISPUTE_NEGOTIABLE_KEY] == pytest.approx(10_000_000 - 3_000_000)
