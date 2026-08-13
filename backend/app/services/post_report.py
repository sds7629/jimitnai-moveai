"""사후보고 에이전트 (agents/post-report.md).

사건이 끝난 뒤 "우리가 맞았는가, 틀렸는가"를 숨기지 않고 정리한다 --
simulation-supply-chain-tool.md §8.2의 12개 섹션을 하나도 빠짐없이 채우고,
예상과 실제를 좋게 포장하지 않는다.

## 이 웨이브의 스코프 결정 (반드시 지킬 것)

이 시스템 어디에도 "실적 확정값"(실측 손실, 실제 완료 시각 등)을 입력받는
API가 없다 -- 8개 웨이브 전체를 통틀어 의도된 제한이다(§6 실시간 외부연동
제외와 같은 이유). 그래서:

  - "실제 진행 과정"/"실제 손실" 관련 섹션은 항상 `actual_status="미확정"`을
    명시하고 예상값(시뮬레이션 결과)만 채운다.
  - §8.1이 이미 이 상황을 허용한다("실적값이 늦게 확정되는 경우 운영 사건은
    종료하되 사후보고서를 잠정 상태로 두고, 비용 확정 후 최종 버전을
    생성한다"). 이 시스템엔 실적을 나중에라도 입력할 방법이 없으므로 이번
    스코프에서 생성되는 사후보고서는 **항상** `report_status="잠정"`이다.
  - "회피한 손실"은 실측치가 없어 "예상 회피손실"(baseline 후보의
    expected_loss - 승인된 후보의 expected_loss)로 이름 붙이고 추정치임을
    명시한다 (app/services/cost_attribution.compute_expected_avoided_loss).
  - "시뮬레이션 오차"는 실적 데이터 없이는 계산 불가능하므로 "오차 계산 불가"
    로 명시하고, 대신 각 시뮬레이션의 confidence/sensitivity_variables/
    assumption을 참고 정보로 보여준다.

## 별도 저장 테이블을 만들지 않는 이유

`GET /incidents/{id}/post-report`는 호출될 때마다 매번 재계산한다. 페르소나
문서(agents/post-report.md)는 "별도 저장 테이블 필요 시 decision_packages/
simulation_results에서 파생"이라고 힌트를 주지만, 실제로 살펴보면 12개 섹션
전부가 이미 존재하는 테이블(incidents/operational_snapshots/
response_candidates/simulation_results/approvals/audit_log/
decision_packages)에서 100% 파생 가능하다 -- 이 함수 자체가 그 증거다. 사후
보고서 전용 테이블을 새로 만들면 (a) 원본 데이터가 바뀔 일이 없는 마당에
캐시 무효화 로직만 추가되고 (b) "잠정" 상태 자체가 확정 시점이 없어 언제
다시 계산해야 하는지 판단할 근거도 없다. 반면 매번 재계산은 비용이 저렴하다
(DB 쿼리 몇 번, LLM 호출 전혀 없음 -- 이 웨이브 자체가 "LLM 호출 없이 집계"
웨이브다). 그래서 새 테이블을 만들지 않는다.

모든 함수는 동기(`def`)다 -- LLM 텍스트 생성 호출이 전혀 없고,
`search_similar_chunks`(cost_attribution 경유)의 임베딩 호출도 반복 호출이
아닌 단발성 블로킹 함수 호출 하나뿐이라 CLAUDE.md 비동기 처리 원칙상 async로
감쌀 실익이 없다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.approvals import ApprovalRepository
from app.repositories.incidents import IncidentRepository
from app.repositories.operational_snapshots import OperationalSnapshotRepository
from app.repositories.response_candidates import ResponseCandidateRepository
from app.repositories.simulation_results import SimulationResultRepository
from app.services.cost_attribution import (
    baseline_candidate_with_earliest_sim,
    classify_cost_attribution,
    compute_expected_avoided_loss,
    final_approved_candidate,
)
from app.services.communication import sop_status_for_incident
from app.services.execution_tracking import timeline_for_incident
from app.services.operational_graph import IncidentNotFoundError  # re-exported for API layer

__all__ = ["build_post_report", "IncidentNotFoundError", "REPORT_STATUS_PROVISIONAL", "ACTUAL_STATUS_UNCONFIRMED"]

REPORT_STATUS_PROVISIONAL = "잠정"
ACTUAL_STATUS_UNCONFIRMED = "미확정"

# 사용자 화면에 그대로 노출되는 문구다 -- 내부 문서 섹션 번호(§8.1)나 웨이브/모듈
# 이름을 인용하지 않는다(실제 사용자는 그게 뭘 가리키는지 알 수 없다). 병합 전
# 리뷰에서 발견: 이 상수의 이전 버전이 "8개 웨이브 전체의 의도된 스코프 제한"·
# "simulation-supply-chain-tool.md §8.1" 같은 내부 개발 용어를 그대로 노출하고
# 있었다.
SCOPE_LIMITATION_NOTE = (
    "이 시스템은 아직 실적(실제 손실 금액, 실제 완료 시각 등)을 입력하는 기능을 "
    "제공하지 않습니다. 그래서 이 보고서는 실적이 확정되기 전까지 항상 '잠정' "
    "상태로 표시되며, 실적이 확정된 이후의 최종 보고서 작성은 담당자가 직접 "
    "검토해 별도로 확정해야 합니다."
)


def _to_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _unavailable(reason: str) -> dict[str, Any]:
    return {"available": False, "reason": reason}


# ------------------------------------------------------------------
# 섹션 1: 사건 개요와 발생시점
# ------------------------------------------------------------------


def _section_1_overview(incident) -> dict[str, Any]:
    return {
        "incident_id": incident.id,
        "type": incident.type,
        "location": incident.location,
        "occurred_at": incident.occurred_at,
        "status": incident.status,
        "duplicate_of_incident_id": incident.duplicate_of_incident_id,
        "affected_targets": incident.affected_targets or {},
        "assumptions_at_intake": list(incident.assumptions or []),
        "created_at": incident.created_at,
    }


# ------------------------------------------------------------------
# 섹션 2 / 7: 최초 예상과 실제 진행 과정 / 예상 손실과 실제 손실
# (같은 baseline/승인후보 시뮬레이션 자료를 재사용한다)
# ------------------------------------------------------------------


def _candidate_summary(candidate, sim) -> dict[str, Any]:
    if candidate is None:
        return {"available": False}
    summary: dict[str, Any] = {
        "available": True,
        "candidate_id": candidate.id,
        "candidate_type": candidate.candidate_type,
        "description": candidate.description,
        "start_time_variant": candidate.start_time_variant,
    }
    if sim is None:
        summary["simulation"] = {"available": False, "reason": "이 후보의 시뮬레이션 결과가 없음"}
    else:
        summary["simulation"] = {
            "available": True,
            "expected_loss": _to_float(sim.expected_loss),
            "p90": _to_float(sim.p90),
            "cvar": _to_float(sim.cvar),
            "confidence": _to_float(sim.confidence),
            "data_version": sim.data_version,
            "scenario_version": sim.scenario_version,
            "calculated_at": sim.created_at,
        }
    return summary


def _expected_progress(db: Session, incident_id: int) -> dict[str, Any]:
    """baseline(무대응)과 최종 승인 후보 각각의 예상 시뮬레이션 결과. baseline은
    §9 baseline 불변성 요구에 따라 첫 시뮬레이션 결과로 고정한다(가장 최근
    버전을 임의로 가져오지 않음) -- app/services/cost_attribution.py 참고."""

    baseline_candidate, baseline_sim = baseline_candidate_with_earliest_sim(db, incident_id)
    approved_candidate, approved_sim = final_approved_candidate(db, incident_id)
    return {
        "baseline": _candidate_summary(baseline_candidate, baseline_sim),
        "approved_candidate": _candidate_summary(approved_candidate, approved_sim),
    }


def _section_2_expected_vs_actual_progress(db: Session, incident_id: int) -> dict[str, Any]:
    return {
        "expected": _expected_progress(db, incident_id),
        "actual_status": ACTUAL_STATUS_UNCONFIRMED,
        "actual_progress": _unavailable(SCOPE_LIMITATION_NOTE),
    }


def _section_7_expected_vs_actual_loss(db: Session, incident_id: int) -> dict[str, Any]:
    return {
        "expected_loss": _expected_progress(db, incident_id),
        "actual_status": ACTUAL_STATUS_UNCONFIRMED,
        "actual_loss": _unavailable(SCOPE_LIMITATION_NOTE),
    }


# ------------------------------------------------------------------
# 섹션 3: 주요 동적 변수의 변화
# ------------------------------------------------------------------


def _summarize_snapshot_changes(history: list) -> list[dict[str, Any]] | list[str]:
    if not history:
        return ["operational_snapshots 이력이 없음"]
    if len(history) == 1:
        return ["스냅샷이 1개뿐이라 버전 간 변화 이력이 없음 (최초 스냅샷만 존재)"]

    changes: list[dict[str, Any]] = []
    for prev, curr in zip(history, history[1:]):
        parts: list[str] = []
        if prev.quality_mode != curr.quality_mode:
            parts.append(f"quality_mode: '{prev.quality_mode}' -> '{curr.quality_mode}'")

        prev_assumptions = {str(a) for a in (prev.assumptions or [])}
        curr_assumptions = {str(a) for a in (curr.assumptions or [])}
        added = sorted(curr_assumptions - prev_assumptions)
        removed = sorted(prev_assumptions - curr_assumptions)
        if added:
            parts.append(f"가정 추가: {added}")
        if removed:
            parts.append(f"가정 제거: {removed}")

        if not parts:
            parts.append("quality_mode/assumptions 변경 없음")

        changes.append(
            {
                "from_snapshot_id": prev.id,
                "to_snapshot_id": curr.id,
                "from_created_at": prev.created_at,
                "to_created_at": curr.created_at,
                "summary": " / ".join(parts),
            }
        )
    return changes


def _section_3_dynamic_variable_changes(db: Session, incident_id: int) -> dict[str, Any]:
    history = OperationalSnapshotRepository(db).history_for_incident(incident_id)
    return {
        "snapshot_count": len(history),
        "versions": [
            {
                "snapshot_id": s.id,
                "data_version": s.data_version,
                "scenario_version": s.scenario_version,
                "quality_mode": s.quality_mode,
                "freshness_seconds": s.freshness_seconds,
                "coverage_ratio": _to_float(s.coverage_ratio),
                "assumptions": list(s.assumptions or []),
                "created_at": s.created_at,
            }
            for s in history
        ],
        "changes_summary": _summarize_snapshot_changes(history),
    }


# ------------------------------------------------------------------
# 섹션 4: 검토한 대응안과 제외 사유
# ------------------------------------------------------------------


def _section_4_candidates_reviewed(db: Session, incident_id: int) -> dict[str, Any]:
    candidates = ResponseCandidateRepository(db).for_incident(incident_id)
    items = [
        {
            "candidate_id": c.id,
            "candidate_type": c.candidate_type,
            "description": c.description,
            "start_time_variant": c.start_time_variant,
            "validation_status": c.validation_status,
            "exclusion_category": c.exclusion_category,
            "exclusion_detail": c.exclusion_detail,
            "preconditions": list(c.preconditions or []),
        }
        for c in candidates
    ]
    excluded = [c for c in items if c["validation_status"] not in ("가능",)]
    return {
        "total_count": len(items),
        "excluded_count": len(excluded),
        "candidates": items,
    }


# ------------------------------------------------------------------
# 섹션 5: 최종 결정과 승인자
# ------------------------------------------------------------------


def _approval_summary(approval) -> dict[str, Any]:
    return {
        "approval_id": approval.id,
        "decision_type": approval.decision_type,
        "reason": approval.reason,
        "approver": approval.approver,
        "decided_at": approval.decided_at,
        "data_version_ref": approval.data_version_ref,
        "scenario_version_ref": approval.scenario_version_ref,
    }


def _section_5_final_decision(db: Session, incident_id: int) -> dict[str, Any]:
    approvals = ApprovalRepository(db).for_incident(incident_id)
    if not approvals:
        return {
            "approvals_history": [],
            "final_decision": _unavailable("이 사건에 대한 승인/반려 이력(approvals)이 없음"),
        }
    return {
        "approvals_history": [_approval_summary(a) for a in approvals],
        "final_decision": {"available": True, **_approval_summary(approvals[-1])},
    }


# ------------------------------------------------------------------
# 섹션 6: 관계자별 SOP 발송·수신·수락·실행 이력
# ------------------------------------------------------------------


def _section_6_sop_history(db: Session, incident_id: int) -> dict[str, Any]:
    """execution-tracking/communication 웨이브가 이미 만든 sop_id별 그룹핑
    조회 로직(app/services/communication.sop_status_for_incident)을 그대로
    재사용한다 -- 여기서 audit_log를 새로 파싱하지 않는다."""

    dispatches = sop_status_for_incident(db, incident_id)
    return {
        "sop_count": len(dispatches),
        "dispatches": dispatches,
    }


# ------------------------------------------------------------------
# 섹션 8: 회피한 손실과 추가 발생 비용 (예상 회피손실 - §9)
# ------------------------------------------------------------------


def _section_8_avoided_loss(db: Session, incident_id: int) -> dict[str, Any]:
    avoided = compute_expected_avoided_loss(db, incident_id)
    return {
        "expected_avoided_loss": avoided,
        "additional_cost_incurred": _unavailable(
            "실제 비용 데이터를 아직 입력받을 수 없어 추가 발생 비용을 금액으로 산출하지는 "
            "못합니다. 다만 아래 '자원 확보 실패·실행 편차 이력'에 기록된 사건들이 추가 비용이 "
            "발생했을 가능성이 있는 지점을 보여줍니다."
        ),
    }


# ------------------------------------------------------------------
# 섹션 9: LD·D&D 귀책 및 비용 부담 주체 -- cost_attribution 결과를 그대로 포함
# ------------------------------------------------------------------


def _section_9_cost_attribution(db: Session, incident_id: int) -> dict[str, Any]:
    return classify_cost_attribution(db, incident_id)


# ------------------------------------------------------------------
# 섹션 10: 시뮬레이션 오차와 가정의 영향
# ------------------------------------------------------------------


def _section_10_simulation_error(db: Session, incident_id: int) -> dict[str, Any]:
    candidates = ResponseCandidateRepository(db).for_incident(incident_id)
    sim_repo = SimulationResultRepository(db)

    per_candidate: list[dict[str, Any]] = []
    for c in candidates:
        sim = sim_repo.latest_for_candidate(c.id)
        if sim is None:
            continue
        per_candidate.append(
            {
                "candidate_id": c.id,
                "candidate_type": c.candidate_type,
                "confidence": _to_float(sim.confidence),
                "sensitivity_variables": list(sim.sensitivity_variables or []),
                "assumption": sim.assumption or {},
                "data_version": sim.data_version,
                "scenario_version": sim.scenario_version,
                "calculated_at": sim.created_at,
            }
        )

    return {
        "error_calculable": False,
        "reason": (
            "실적 데이터(실제 손실, 실제 완료 시각 등)가 아직 없어 예측과 실측의 차이"
            "(시뮬레이션 오차)를 계산할 수 없습니다. 실적이 확정되면 최종 보고서에 반영될 "
            "항목입니다."
        ),
        "candidates": per_candidate,
    }


# ------------------------------------------------------------------
# 섹션 11: 자원 확보 실패, 실행 편차와 에스컬레이션 이력
# ------------------------------------------------------------------


def _section_11_deviation_history(db: Session, incident_id: int) -> dict[str, Any]:
    events = timeline_for_incident(db, incident_id)
    deviation_events = [e for e in events if e["is_deviation_event"]]
    return {
        "deviation_event_count": len(deviation_events),
        "events": deviation_events,
    }


# ------------------------------------------------------------------
# 섹션 12: 향후 SOP·모델·데이터 개선사항
# ------------------------------------------------------------------


def _section_12_future_improvements(
    incident_id: int,
    candidates_section: dict[str, Any],
    deviation_section: dict[str, Any],
    sop_section: dict[str, Any],
) -> list[dict[str, str]]:
    """빈 배열/뻔한 말 금지 -- 이 시스템이 실제로 겪은 구체적인 스코프 제한과
    이번 사건의 실제 데이터를 근거로 작성한다."""

    items: list[dict[str, str]] = [
        {
            "category": "실적 확정 데이터 입력 기능 부재",
            "description": (
                "실적(실제 손실 금액, 실제 완료 시각 등)을 입력하는 기능이 아직 없어 모든 "
                "사후보고서가 계속 '잠정' 상태로 남습니다. 담당자가 실적을 입력하고, 그 값을 "
                "반영해 보고서를 '확정' 상태로 전환하는 절차가 추가로 필요합니다."
            ),
        },
        {
            "category": "실행 편차 감지 범위의 한계",
            "description": (
                "현재 실행 편차 감지는 '기한 내 미수락'과 '계획보다 지연된 완료' 2가지 조건만 "
                "확인합니다. 운송·재고·생산 상태 이탈, 확보 자원의 취소·충돌, 신규 사건 발견 같은 "
                "나머지 조건은 관련 운영 시스템과의 실시간 연동이 없어 아직 판단할 수 없습니다. "
                "이 부분을 보완하려면 운송관리·자재관리 시스템과의 연동이 필요합니다."
            ),
        },
        {
            "category": "비용 귀속 분류의 한계",
            "description": (
                "비용 귀속 분류는 계약 조항 검색 결과를 기반으로 한 참고용 추정치이며, 실제 법무 "
                "검토를 대체하지 않습니다. 이 사건과 명확히 연결된 계약 조항을 찾지 못하면 전액 "
                "'분쟁·협상 가능 금액'으로 분류되므로, 법무팀 검토 결과를 반영해 재분류하는 절차가 "
                "필요합니다."
            ),
        },
    ]

    if candidates_section["total_count"] <= 1:
        items.append(
            {
                "category": "대응안 다양성 부족",
                "description": (
                    f"baseline(무대응)을 제외하면 검토된 대응안이 "
                    f"{max(candidates_section['total_count'] - 1, 0)}개뿐이었습니다. 대응안 후보가 "
                    "거의 나오지 않은 경우이므로, 관련 플레이북·과거 사례 데이터가 충분한지 점검이 "
                    "필요합니다."
                ),
            }
        )

    if deviation_section["deviation_event_count"] > 0:
        items.append(
            {
                "category": "실행 편차 반복 여부 점검",
                "description": (
                    f"사건 {incident_id}: 실행 편차/에스컬레이션이 {deviation_section['deviation_event_count']}"
                    "건 기록되었습니다. 반복되는 편차 사유가 있다면 해당 SOP의 완료기한 산정 방식이나 "
                    "수락 절차 자체를 개정 후보로 등록해야 합니다."
                ),
            }
        )

    if sop_section["sop_count"] == 0:
        items.append(
            {
                "category": "SOP 발송 이력 없음",
                "description": (
                    "역할별 SOP 발송 이력이 전혀 없습니다. 이 사건이 아직 승인 단계까지 가지 "
                    "않았는지, 아니면 승인은 됐는데 SOP 발송이 누락된 것인지 확인이 필요합니다."
                ),
            }
        )

    return items


# ------------------------------------------------------------------
# 사후보고서 조립
# ------------------------------------------------------------------


def build_post_report(db: Session, incident_id: int) -> dict[str, Any]:
    """GET /incidents/{id}/post-report의 서비스 로직. 12개 섹션을 전부 필드로
    강제한다(선택 필드 금지) -- 데이터가 없는 섹션도 `available=False` 형태의
    구조화된 값으로 채워지며, 키 자체가 누락되는 일은 없다."""

    incident = IncidentRepository(db).get(incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"incident {incident_id} not found")

    section_4 = _section_4_candidates_reviewed(db, incident_id)
    section_6 = _section_6_sop_history(db, incident_id)
    section_11 = _section_11_deviation_history(db, incident_id)

    sections = {
        "1_사건_개요와_발생시점": _section_1_overview(incident),
        "2_최초_예상과_실제_진행_과정": _section_2_expected_vs_actual_progress(db, incident_id),
        "3_주요_동적_변수의_변화": _section_3_dynamic_variable_changes(db, incident_id),
        "4_검토한_대응안과_제외_사유": section_4,
        "5_최종_결정과_승인자": _section_5_final_decision(db, incident_id),
        "6_SOP_발송_수신_수락_실행_이력": section_6,
        "7_예상_손실과_실제_손실": _section_7_expected_vs_actual_loss(db, incident_id),
        "8_회피한_손실과_추가_발생_비용": _section_8_avoided_loss(db, incident_id),
        "9_LD_DND_귀책_및_비용_부담_주체": _section_9_cost_attribution(db, incident_id),
        "10_시뮬레이션_오차와_가정의_영향": _section_10_simulation_error(db, incident_id),
        "11_자원_확보_실패_실행_편차와_에스컬레이션_이력": section_11,
        "12_향후_SOP_모델_데이터_개선사항": _section_12_future_improvements(
            incident_id, section_4, section_11, section_6
        ),
    }

    return {
        "incident_id": incident_id,
        "report_status": REPORT_STATUS_PROVISIONAL,
        "actual_status": ACTUAL_STATUS_UNCONFIRMED,
        "scope_limitation_note": SCOPE_LIMITATION_NOTE,
        "generated_at": datetime.now(timezone.utc),
        "sections": sections,
    }
