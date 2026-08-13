"""커뮤니케이션 에이전트 (agents/communication-sop.md).

승인된 결정을 실행 현장의 언어로 번역해 역할별(항만/운송/공장/영업/계약 담당자)
SOP 메시지로 "발송"한다. 실제 사내 메신저 연동은 스코프 밖이므로(ARCHITECTURE.md
§6) 발송은 로그 기록(`audit_log`)과 스텁 함수 호출로만 구현한다. LLM 호출도
없다 -- 이미 DB에 있는 정보(decision_package/response_candidates/approval)를
역할별 템플릿으로 조합하는 순수 로직이라 모든 함수가 동기(`def`)다 (CLAUDE.md
비동기 처리 원칙: 블로킹 I/O가 없으면 억지로 async를 쓰지 않는다).

## sop_id 관례 (다음 웨이브 execution-tracking을 위한 설계 결정)

이번 웨이브는 SOP 발송/상태 전용 테이블을 새로 만들지 않는다. 역할별 SOP를
발송할 때마다 `audit_log`에 `event_type='sop_dispatched'`인 행을 하나씩
추가하고(항만/운송/공장/영업/계약 = 최대 5개 행), **그 audit_log 행의 `id`가
곧 `sop_id`다.** 다음 웨이브(execution-tracking)는 이 `sop_id`를
`payload={"sop_id": <원래 발송 행의 id>, "status": "수신"|"수락"|"완료"|"실패", ...}`
형태의 후속 `audit_log` 행으로 참조해 상태를 이어받는 것으로 설계했다 --
`GET /incidents/{id}/sop-status`(app/api/sop_dispatch.py)가 이 관례를 그대로
읽어 자동으로 상태를 채운다. `event_type` 이름 자체는 이 모듈이 전혀 모르므로
execution-tracking이 새 이벤트 타입을 추가하는 것만으로 이 엔드포인트의 응답이
채워진다.

## 승인 + 자원확정 가드에 대한 판단 근거

이 시스템에는 "실행 자원 확정"을 위한 별도 테이블/단계가 없다(오케스트레이션
웨이브 문서 -- app/services/orchestration.py의 `_approve` 주석: "실행 자원
확정과 SOP 배포는 communication-sop 웨이브의 몫이다 -- 이 상태 전이 자체가 그
웨이브가 기다리는 신호다"). 따라서 이 모듈은 `incidents.status == '승인'`을
"승인 결정 + 자원확정 완료"를 함께 나타내는 신호로 간주한다. 이는
orchestration이 승인/조건부승인 시에만 이 상태로 전이시키고, 수정요청/반려/
기한초과는 절대 이 상태로 전이시키지 않기 때문에 안전한 판단이다 -- 별도의
자원확정 단계가 실제로 생기면(예: 예약 실패 시 되돌리는 로직) 그 웨이브가 이
가드 조건을 그 신호로 교체하면 된다.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.approval import Approval
from app.models.document import Document
from app.models.incident import Incident
from app.models.response_candidate import ResponseCandidate
from app.repositories.approvals import ApprovalRepository
from app.repositories.audit_log import AuditLogRepository
from app.repositories.decision_packages import DecisionPackageRepository
from app.repositories.documents import DocumentRepository
from app.repositories.incidents import IncidentRepository
from app.repositories.response_candidates import ResponseCandidateRepository
from app.services.operational_graph import IncidentNotFoundError  # re-exported for API layer convenience

__all__ = [
    "dispatch_sop",
    "sop_status_for_incident",
    "ApprovalNotFoundError",
    "SopDispatchNotAllowedError",
    "IncidentNotFoundError",
    "ROLES",
]

logger = logging.getLogger(__name__)

# 승인 상태 전이의 근거가 되는 값들 -- orchestration.APPROVED_STATUS /
# CLIENT_DECISION_TYPES와 반드시 동기화된 상수다. 이 모듈이 orchestration.py를
# 직접 import해 상수를 재사용하지 않는 이유: 두 웨이브의 결합을 상수 하나에
# 묶어두면 orchestration이 이후 리팩터링될 때 이 가드가 조용히 깨질 수 있다 --
# 값 자체는 DB 스키마의 CHECK 제약(db/init/002-schema.sql)에도 고정돼 있으므로
# 여기서 별도로 명시해도 이중 관리 부담이 크지 않다.
APPROVAL_DECISION_TYPES_ELIGIBLE_FOR_DISPATCH: tuple[str, ...] = ("승인", "조건부승인")
RESOURCE_CONFIRMED_INCIDENT_STATUS = "승인"

SOP_DISPATCH_EVENT_TYPE = "sop_dispatched"
DISPATCH_ACTOR = "communication-sop-service"

# 5개 담당자 유형, §6.2 순서 그대로 (항만 -> 운송 -> 공장 -> 영업 -> 계약).
ROLES: tuple[str, ...] = ("항만", "운송", "공장", "영업", "계약")

UNKNOWN = "미상"  # 지어내지 않고 명시적으로 "미상"이라고 표기하기 위한 placeholder.

# GET /sop-status가 후속 이벤트에서 인지하는 상태값 -- execution-tracking
# 웨이브가 payload={"sop_id":..., "status": <이 중 하나>}로 기록해주면 이
# 편의 필드(received_at/accepted_at/completed_at/failed_at)가 자동으로
# 채워진다. 다른 이름의 status 값이 와도 무시되지 않는다 -- `events`
# 배열에는 어떤 event_type/status든 그대로 원본이 남으므로, 프론트가 이
# 편의 필드 대신 events를 직접 읽어도 정보 손실이 없다.
STATUS_TIMESTAMP_FIELD_BY_STATUS: dict[str, str] = {
    "수신": "received_at",
    "수락": "accepted_at",
    "완료": "completed_at",
    "실패": "failed_at",
}


class ApprovalNotFoundError(LookupError):
    """No approval with the given id exists."""


class SopDispatchNotAllowedError(ValueError):
    """승인/조건부승인이 아니거나, incidents.status가 '승인'(자원확정 완료
    신호)이 아니어서 SOP를 발송할 수 없다. API 레이어가 400/409로 변환한다."""


# ------------------------------------------------------------------
# Context gathering -- pulls together everything §6.2's 9 required items
# need, from decision_packages/response_candidates/approvals. Nothing here
# invents data: every field either comes from an existing row or falls back
# to UNKNOWN.
# ------------------------------------------------------------------


@dataclass
class _MessageContext:
    incident: Incident
    approval: Approval
    deadline: datetime | None
    deadline_basis: str | None
    impact_if_exceeded: str | None
    no_action_summary: dict[str, Any] | None
    top_candidate: ResponseCandidate | None
    top_candidate_rank_info: dict[str, Any] | None
    reference_documents: list[Document] = field(default_factory=list)

    @property
    def affected_targets(self) -> dict[str, Any]:
        return self.incident.affected_targets or {}

    def targets_for(self, key: str) -> list[Any] | str:
        """A specific affected_targets sub-list (containers/parts/
        production_orders/customers), or UNKNOWN if the incident's
        affected_targets never recorded that key at all -- an empty list
        (the key exists but nothing was recorded under it) is a real,
        different answer from "we don't know", so only a missing key
        collapses to UNKNOWN."""

        targets = self.affected_targets
        if key not in targets:
            return UNKNOWN
        return list(targets.get(key) or [])

    @property
    def deadline_text(self) -> str:
        return self.deadline.isoformat() if self.deadline is not None else UNKNOWN

    @property
    def scenario_version(self) -> str:
        return self.approval.scenario_version_ref or UNKNOWN

    @property
    def data_version(self) -> str:
        return self.approval.data_version_ref or UNKNOWN

    @property
    def reference_documents_by_type(self) -> dict[str, list[dict[str, Any]]]:
        by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for doc in self.reference_documents:
            by_type[doc.doc_type].append({"id": doc.id, "title": doc.title, "doc_type": doc.doc_type})
        return dict(by_type)


def _build_message_context(db: Session, incident: Incident, approval: Approval) -> _MessageContext:
    """response-optimization이 이미 만들어 둔 decision_packages.package를
    재사용한다 -- 여기서 새로 계산/추론하지 않는다. 승인 이후 새 패키지가 또
    쌓였을 수 있으므로(수정요청 재사이클 등) latest_for_incident로 항상 최신
    패키지를 읽는다."""

    package_row = DecisionPackageRepository(db).latest_for_incident(incident.id)
    package = package_row.package if package_row is not None else {}

    deadline = package_row.recommended_deadline if package_row is not None else None
    deadline_detail = (package.get("recommended_deadline") or {}).get("detail") or {}
    deadline_basis = deadline_detail.get("basis")
    impact_if_exceeded = deadline_detail.get("impact_if_exceeded")

    no_action_summary = (package.get("now_vs_6h_vs_no_action") or {}).get("no_action")

    # "추천 대응안" -- ranked_candidates.ranked는 이미 composite_score 오름차순
    # (rank 1 = 최우선)으로 정렬돼 있다(response_optimization.rank_candidates).
    # baseline(현재 조치 없음)이 우연히 1위인 극단적인 경우를 제외하고, 실제로
    # "실행할 대응"을 가리키는 첫 non-baseline 항목을 고른다 -- approvals
    # 테이블 자체에는 "이 후보를 승인했다"는 필드가 없어 이것이 이번 스코프의
    # 판단 근거다(코드 주석으로 명시).
    ranked = ((package.get("ranked_candidates") or {}).get("ranked")) or []
    top_rank_info = next((r for r in ranked if r.get("candidate_type") != "baseline"), None)
    if top_rank_info is None and ranked:
        top_rank_info = ranked[0]

    top_candidate: ResponseCandidate | None = None
    reference_documents: list[Document] = []
    if top_rank_info is not None:
        candidate_id = top_rank_info.get("candidate_id")
        if candidate_id is not None:
            top_candidate = ResponseCandidateRepository(db).get(candidate_id)
            if top_candidate is not None:
                doc_repo = DocumentRepository(db)
                for doc_id in top_candidate.reference_document_ids or []:
                    doc = doc_repo.get(doc_id)
                    if doc is not None:
                        reference_documents.append(doc)

    return _MessageContext(
        incident=incident,
        approval=approval,
        deadline=deadline,
        deadline_basis=deadline_basis,
        impact_if_exceeded=impact_if_exceeded,
        no_action_summary=no_action_summary,
        top_candidate=top_candidate,
        top_candidate_rank_info=top_rank_info,
        reference_documents=reference_documents,
    )


# ------------------------------------------------------------------
# Shared template pieces -- the 9 common items every message must carry
# (simulation-supply-chain-tool.md §6.2). Role-specific builders below
# supply "해야 할 조치" and the role's own highlighted fields; everything
# else is assembled here once so the 9 required items never drift between
# roles.
# ------------------------------------------------------------------


def _reason_for_action(ctx: _MessageContext) -> str:
    """조치가 필요한 이유 -- 사건 유형/위치 + (있다면) 결정기한의 근거 문장을
    합쳐 담당자가 "왜 지금 이걸 해야 하는지"를 한 문장으로 읽게 한다."""

    base = f"{ctx.incident.type} 사건({ctx.incident.location}) 대응을 위해 담당자 승인({ctx.approval.decision_type})이 완료됨"
    if ctx.deadline_basis:
        return f"{base} -- {ctx.deadline_basis}"
    return base


def _expected_impact_if_not_executed(ctx: _MessageContext) -> str:
    """미실행 시 예상 영향 -- decision_package의 결정기한 근거(§10)와
    no_action(현행 유지) 시뮬레이션 결과를 함께 보여준다. 둘 다 없으면(=
    decision_package가 아직 없는 극단적인 경우) 정직하게 UNKNOWN."""

    parts: list[str] = []
    if ctx.impact_if_exceeded:
        parts.append(ctx.impact_if_exceeded)
    if ctx.no_action_summary:
        expected_loss = ctx.no_action_summary.get("expected_loss")
        p90 = ctx.no_action_summary.get("p90")
        if expected_loss is not None or p90 is not None:
            parts.append(f"현행 유지(no_action) 시뮬레이션: expected_loss={expected_loss}, p90={p90}")
    return " / ".join(parts) if parts else UNKNOWN


def _common_fields(ctx: _MessageContext) -> dict[str, Any]:
    """§6.2가 요구하는 9개 공통 항목 중, 역할과 무관하게 동일한 값을 갖는
    부분(담당자와 완료기한/조치가 필요한 이유/관련 컨테이너·부품·생산오더/
    참고한 SOP와 계약 조항/미실행 시 예상 영향/승인자와 시나리오 버전/
    수신확인·수락·완료보고 방법/에스컬레이션 경로). "해야 할 조치"만 역할별
    빌더가 채운다."""

    return {
        "completion_deadline": ctx.deadline_text,
        "reason": _reason_for_action(ctx),
        "related_containers": ctx.targets_for("containers"),
        "related_parts": ctx.targets_for("parts"),
        "related_production_orders": ctx.targets_for("production_orders"),
        "referenced_documents": ctx.reference_documents_by_type or UNKNOWN,
        "expected_impact_if_not_executed": _expected_impact_if_not_executed(ctx),
        "approver": ctx.approval.approver,
        "approval_decision_type": ctx.approval.decision_type,
        "scenario_version": ctx.scenario_version,
        "data_version": ctx.data_version,
        # 수신확인/수락/완료보고 방법 -- 실제 메신저 연동이 없는 이번 스코프의
        # 스텁 절차. execution-tracking 웨이브가 실제 API(PATCH /sop/{sop_id}
        # /status, ARCHITECTURE.md §7.1)를 붙이면 이 문구가 그 절차를 안내하는
        # 문구로 자연스럽게 이어진다.
        "acknowledgment_method": (
            "사내 메신저 스텁 채널에서 본 SOP 수신 확인 후 회신, 작업 수락 시 '수락' 응답, "
            "완료 시 완료 보고(사진/수량 등 근거 포함)를 실행 추적 화면에 제출"
        ),
        "escalation_path": (
            "완료기한 초과 또는 실행 중 실패 시 즉시 상위 책임자(오케스트레이션 담당)에게 "
            "에스컬레이션 -- 시스템은 결정기한 초과를 자동 기록하며(agents/orchestration.md "
            "check_deadline_overrun), 편차가 허용범위를 넘으면 Impact DAG 재계산 대상이 됨"
        ),
    }


def _render_message_text(role: str, action: str, common: dict[str, Any], role_specific: dict[str, Any]) -> str:
    """로그/스텁 발송에 실릴 사람이 읽는 메시지 전문. 실제 메신저 포맷팅이
    아니라 순수 텍스트 조합 -- 나중에 실제 연동으로 교체될 때 이 함수만 바뀌면
    된다."""

    lines = [
        f"[{role} 담당자 SOP] 조치 필요",
        f"- 해야 할 조치: {action}",
        f"- 담당자/완료기한: {role} 담당자 / {common['completion_deadline']}",
        f"- 조치가 필요한 이유: {common['reason']}",
        f"- 관련 컨테이너: {common['related_containers']}",
        f"- 관련 부품: {common['related_parts']}",
        f"- 관련 생산오더: {common['related_production_orders']}",
        f"- 참고 SOP/계약 조항: {common['referenced_documents']}",
        f"- 미실행 시 예상 영향: {common['expected_impact_if_not_executed']}",
        f"- 승인자/결정유형/시나리오버전: {common['approver']} / {common['approval_decision_type']} / {common['scenario_version']}",
        f"- 수신확인/수락/완료보고: {common['acknowledgment_method']}",
        f"- 에스컬레이션 경로: {common['escalation_path']}",
    ]
    for label, value in role_specific.items():
        lines.append(f"- [{role} 전용] {label}: {value}")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Role-specific builders (simulation-supply-chain-tool.md §6.2) -- kept as
# 5 separate functions per persona doc's requirement, even though they all
# call the same _common_fields() helper above.
# ------------------------------------------------------------------


def _build_port_message(ctx: _MessageContext) -> dict[str, Any]:
    """항만 담당자 -- 우선 반출 대상 컨테이너와 완료기한."""

    common = _common_fields(ctx)
    action = "우선 반출 대상 컨테이너 반출 처리 -- 항만 슬롯/서류 확인 후 즉시 반출 개시"
    role_specific = {
        "priority_release_containers": common["related_containers"],
        "completion_deadline": common["completion_deadline"],
    }
    return {
        "role": "항만",
        "action": action,
        **common,
        "role_specific": role_specific,
        "message_text": _render_message_text("항만", action, common, role_specific),
    }


def _build_transport_message(ctx: _MessageContext) -> dict[str, Any]:
    """운송 담당자 -- 긴급 차량 배차 및 대체 경로."""

    common = _common_fields(ctx)
    action = "긴급 차량 배차 및 대체 운송 경로 확보"
    alternative_route_note = (
        ctx.top_candidate.description if ctx.top_candidate is not None else UNKNOWN
    )
    role_specific = {
        "emergency_vehicle_dispatch_required": True,
        "alternative_route_note": alternative_route_note,
        "related_containers": common["related_containers"],
    }
    return {
        "role": "운송",
        "action": action,
        **common,
        "role_specific": role_specific,
        "message_text": _render_message_text("운송", action, common, role_specific),
    }


def _build_factory_message(ctx: _MessageContext) -> dict[str, Any]:
    """공장 담당자 -- 재고 소진 예상시각과 생산순서 변경안."""

    common = _common_fields(ctx)
    action = "생산 순서 변경 적용 및 재고 소진 대비"
    production_sequence_change_proposal = (
        ctx.top_candidate.description if ctx.top_candidate is not None else UNKNOWN
    )
    role_specific = {
        "inventory_depletion_expected_at": common["completion_deadline"],
        "production_sequence_change_proposal": production_sequence_change_proposal,
        "related_parts": common["related_parts"],
        "related_production_orders": common["related_production_orders"],
    }
    return {
        "role": "공장",
        "action": action,
        **common,
        "role_specific": role_specific,
        "message_text": _render_message_text("공장", action, common, role_specific),
    }


def _build_sales_message(ctx: _MessageContext) -> dict[str, Any]:
    """영업 담당자 -- 영향 고객과 사전 안내 기준."""

    common = _common_fields(ctx)
    action = "영향 고객 대상 사전 안내 실시"
    affected_customers = ctx.targets_for("customers")
    if ctx.no_action_summary and ctx.no_action_summary.get("p90") is not None:
        advance_notice_criteria = (
            f"현행 유지 시 예상 손실(P90) {ctx.no_action_summary.get('p90')} 이상 지연 예상 -- 즉시 사전 안내"
        )
    else:
        advance_notice_criteria = UNKNOWN
    role_specific = {
        "affected_customers": affected_customers,
        "advance_notice_criteria": advance_notice_criteria,
    }
    return {
        "role": "영업",
        "action": action,
        **common,
        "role_specific": role_specific,
        "message_text": _render_message_text("영업", action, common, role_specific),
    }


def _build_contract_message(ctx: _MessageContext) -> dict[str, Any]:
    """계약 담당자 -- LD·D&D 발생 가능성과 귀책 검토 요청."""

    common = _common_fields(ctx)
    action = "LD(지체상금)·D&D(체화료/지체료) 발생 가능성 검토 및 귀책 판단 요청"
    contract_docs = (common["referenced_documents"] or {}).get("계약") if isinstance(common["referenced_documents"], dict) else None
    if ctx.impact_if_exceeded:
        ld_dnd_risk_note = f"완료기한({common['completion_deadline']}) 초과 시 -- {ctx.impact_if_exceeded}"
    else:
        ld_dnd_risk_note = UNKNOWN
    role_specific = {
        "ld_dnd_risk_note": ld_dnd_risk_note,
        "referenced_contract_clauses": contract_docs or UNKNOWN,
    }
    return {
        "role": "계약",
        "action": action,
        **common,
        "role_specific": role_specific,
        "message_text": _render_message_text("계약", action, common, role_specific),
    }


ROLE_BUILDERS: dict[str, Callable[[_MessageContext], dict[str, Any]]] = {
    "항만": _build_port_message,
    "운송": _build_transport_message,
    "공장": _build_factory_message,
    "영업": _build_sales_message,
    "계약": _build_contract_message,
}


# ------------------------------------------------------------------
# "발송" -- 실제 메신저 연동 없이 로그만 남기는 스텁. 실제 연동으로 교체할
# 때는 이 함수의 내부만 바뀌면 되고, dispatch_sop의 나머지 로직/시그니처는
# 그대로 유지된다 (ARCHITECTURE.md §6: 사내 메신저 실연동 제외).
# ------------------------------------------------------------------


def _send_via_stub(role: str, message: dict[str, Any]) -> None:
    logger.info("SOP dispatched (stub, no real messenger call) role=%s message=%s", role, message["message_text"])


def _format_dispatch_result(row: AuditLog) -> dict[str, Any]:
    payload = row.payload or {}
    message = payload.get("message") or {}
    return {
        "sop_id": row.id,
        "incident_id": row.incident_id,
        "role": payload.get("role"),
        "approval_id": payload.get("approval_id"),
        "dispatched_at": row.created_at,
        "action": message.get("action"),
        "message_text": message.get("message_text"),
    }


def dispatch_sop(db: Session, approval_id: int) -> list[dict[str, Any]]:
    """POST /approvals/{id}/dispatch-sop의 서비스 로직.

    가드(둘 다 통과해야 발송):
      1. approval_id가 존재하고, 그 decision_type이 '승인'/'조건부승인'이어야
         함(다른 값이면 SopDispatchNotAllowedError).
      2. 그 approval의 incident.status가 실제로 '승인'이어야 함(=자원확정
         완료 신호, 모듈 docstring 참고). 아니면 SopDispatchNotAllowedError.

    멱등성: 같은 approval_id로 이미 5개 역할 발송이 끝났다면(=audit_log에
    이미 이 approval_id를 참조하는 sop_dispatched 행들이 있다면) 다시
    발송하지 않고 기존 발송 내역을 그대로 반환한다.

    5개 역할은 그냥 순서대로(반복문) 처리한다 -- 블로킹 I/O가 없으므로
    asyncio로 병렬화할 이유가 없다(CLAUDE.md 비동기 처리 원칙 / 작업
    브리핑의 명시적 지시)."""

    approval = ApprovalRepository(db).get(approval_id)
    if approval is None:
        raise ApprovalNotFoundError(f"approval {approval_id} not found")

    if approval.decision_type not in APPROVAL_DECISION_TYPES_ELIGIBLE_FOR_DISPATCH:
        raise SopDispatchNotAllowedError(
            f"approval {approval_id}의 decision_type={approval.decision_type!r}은(는) "
            f"SOP 발송 대상이 아닙니다 (허용값: {APPROVAL_DECISION_TYPES_ELIGIBLE_FOR_DISPATCH})"
        )

    incident = IncidentRepository(db).get(approval.incident_id)
    if incident is None:
        # FK가 있어 정상적으로는 발생하지 않지만, 방어적으로 처리한다.
        raise IncidentNotFoundError(f"incident {approval.incident_id} not found")

    if incident.status != RESOURCE_CONFIRMED_INCIDENT_STATUS:
        raise SopDispatchNotAllowedError(
            f"incident {incident.id}의 status={incident.status!r}가 "
            f"{RESOURCE_CONFIRMED_INCIDENT_STATUS!r}(승인+자원확정 완료 신호)가 아니어서 "
            "SOP를 발송할 수 없습니다"
        )

    audit_repo = AuditLogRepository(db)
    existing = audit_repo.sop_dispatches_for_approval(incident.id, approval.id)
    if existing:
        return [_format_dispatch_result(row) for row in existing]

    ctx = _build_message_context(db, incident, approval)

    results: list[dict[str, Any]] = []
    for role in ROLES:
        message = ROLE_BUILDERS[role](ctx)
        row = audit_repo.add(
            incident_id=incident.id,
            event_type=SOP_DISPATCH_EVENT_TYPE,
            actor=DISPATCH_ACTOR,
            reason=f"SOP 발송 -- {role} 담당자 (approval_id={approval.id}, decision_type={approval.decision_type})",
            payload={"approval_id": approval.id, "role": role, "message": message},
        )
        _send_via_stub(role, message)
        results.append(_format_dispatch_result(row))

    return results


# ------------------------------------------------------------------
# GET /incidents/{id}/sop-status
# ------------------------------------------------------------------


def _derive_status_fields(followups: list[AuditLog]) -> dict[str, Any]:
    """followups는 이 sop_id를 참조하는(payload["sop_id"] == 그 발송 행의 id)
    후속 audit_log 행들, 오래된 순. execution-tracking 웨이브가 아직 없으므로
    이 후속 이벤트는 지금은 항상 빈 리스트다 -- 이 함수는 그 웨이브가 실제로
    payload={"sop_id":..., "status": "수신"|"수락"|"완료"|"실패"} 형태의 행을
    추가하기 시작하면 자동으로 채워지도록 미리 설계해 둔 것이다."""

    fields: dict[str, Any] = {"received_at": None, "accepted_at": None, "completed_at": None, "failed_at": None}
    latest_status = None
    for row in followups:
        status = (row.payload or {}).get("status")
        if status is None:
            continue
        latest_status = status
        timestamp_field = STATUS_TIMESTAMP_FIELD_BY_STATUS.get(status)
        if timestamp_field is not None and fields[timestamp_field] is None:
            fields[timestamp_field] = row.created_at
    fields["status"] = latest_status or "발송"
    return fields


def _event_dict(row: AuditLog) -> dict[str, Any]:
    return {
        "event_type": row.event_type,
        "actor": row.actor,
        "reason": row.reason,
        "payload": row.payload,
        "created_at": row.created_at,
    }


def sop_status_for_incident(db: Session, incident_id: int) -> list[dict[str, Any]]:
    """GET /incidents/{id}/sop-status의 서비스 로직 -- 이 사건에 대해 지금까지
    쌓인 SOP 관련 audit_log 이벤트를 sop_id별로 묶어 프론트의 발송·수신·수락·
    완료 상태 트래커가 바로 쓸 수 있는 배열로 반환한다.

    설계: sop_dispatched 행 각각이 하나의 sop_id를 만들고, payload["sop_id"]로
    그 id를 참조하는 다른 모든 audit_log 행(어떤 event_type이든)을 그 sop_id의
    후속 이벤트로 묶는다. execution-tracking이 붙기 전인 지금은 각 sop_id의
    events가 항상 비어 있고 status는 "발송"으로만 표시된다 -- 이는 버그가
    아니라 다음 웨이브가 채울 빈 자리다."""

    if IncidentRepository(db).get(incident_id) is None:
        raise IncidentNotFoundError(f"incident {incident_id} not found")

    audit_repo = AuditLogRepository(db)
    timeline = audit_repo.timeline_for_incident(incident_id)

    dispatch_rows = [row for row in timeline if row.event_type == SOP_DISPATCH_EVENT_TYPE]
    dispatch_ids = {row.id for row in dispatch_rows}

    followups_by_sop_id: dict[int, list[AuditLog]] = defaultdict(list)
    for row in timeline:
        if row.id in dispatch_ids:
            continue
        sop_id = (row.payload or {}).get("sop_id")
        if sop_id in dispatch_ids:
            followups_by_sop_id[sop_id].append(row)

    results: list[dict[str, Any]] = []
    for row in dispatch_rows:
        payload = row.payload or {}
        message = payload.get("message") or {}
        followups = followups_by_sop_id.get(row.id, [])
        status_fields = _derive_status_fields(followups)
        results.append(
            {
                "sop_id": row.id,
                "incident_id": incident_id,
                "role": payload.get("role"),
                "approval_id": payload.get("approval_id"),
                "action_summary": message.get("action"),
                "dispatched_at": row.created_at,
                "dispatched_by": row.actor,
                "events": [_event_dict(r) for r in followups],
                **status_fields,
            }
        )

    return results
