"""실행 추적 에이전트 (agents/execution-tracking.md).

발송했다고 끝난 게 아니라는 것을 아는 역할 -- SOP 작업의 상태 전이(발송/수신/
수락/시작/진행/완료/실패)를 `audit_log`에 append-only로 이어 붙이고, 계획값
(decision_package.recommended_deadline)과 실제 진행 상태를 비교해 편차를
감지한다. **이 모듈은 직접 재시뮬레이션을 실행하지 않는다** -- 편차가 감지되면
`app.services.orchestration.handle_execution_deviation`에 위임하는 신호만
발생시킨다 (agents/orchestration.md: "재시뮬레이션 트리거는 이 페르소나만
발생시킨다").

sop_id 관례 (app/services/communication.py가 정한 그대로 따름): 별도 SOP
테이블이 없다 -- 역할별 SOP를 발송할 때 남긴 `audit_log` 행
(`event_type='sop_dispatched'`)의 그 행 자체의 `id`가 곧 `sop_id`다. 상태
전이도 새 `audit_log` 행을 추가하며 `payload={"sop_id": <원래 발송 행의 id>,
"status": ..., "note": ...}`로 이어 붙인다.

블로킹 I/O가 없는 `record_status_transition`/`detect_deviation`/
`timeline_for_incident`는 동기(`def`)로 남긴다. `check_and_handle_deviation`만
`async def`다 -- 편차가 감지되면 `orchestration.handle_execution_deviation`을
거쳐 `simulate_candidates`의 LLM 호출까지 이어질 수 있는 경로이기 때문
(CLAUDE.md 비동기 처리 원칙)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.llm import LLMProvider
from app.models.audit_log import AuditLog
from app.repositories.audit_log import AuditLogRepository
from app.repositories.decision_packages import DecisionPackageRepository
from app.repositories.incidents import IncidentRepository
from app.services.communication import (
    SOP_DISPATCH_EVENT_TYPE,
    IncidentNotFoundError,
    sop_status_for_incident,
)  # IncidentNotFoundError re-exported for API layer convenience
from app.services.orchestration import handle_execution_deviation

__all__ = [
    "record_status_transition",
    "detect_deviation",
    "check_and_handle_deviation",
    "timeline_for_incident",
    "DeviationResult",
    "SopNotFoundError",
    "InvalidSopStatusError",
    "IncidentNotFoundError",
    "VALID_SOP_STATUSES",
    "FAILED_STATUS",
    "COMPLETED_STATUS",
    "STATUS_TRANSITION_EVENT_TYPE",
    "DEVIATION_DETECTED_EVENT_TYPE",
]

logger = logging.getLogger(__name__)

# ARCHITECTURE.md §2 / §7.1, agents/execution-tracking.md 핵심 설계 원칙 --
# 업무 명세 §6.3이 나열하는 7개 상태(발송/수신/수락/시작/진행/완료/실패) 중
# '발송'은 communication-sop 웨이브가 이미 SOP_DISPATCH_EVENT_TYPE으로 남기므로
# 여기서는 그 이후 6개 상태 전이만 다룬다.
VALID_SOP_STATUSES: tuple[str, ...] = ("수신", "수락", "시작", "진행", "완료", "실패")
FAILED_STATUS = "실패"
COMPLETED_STATUS = "완료"

STATUS_TRANSITION_EVENT_TYPE = "sop_status_transition"
DEVIATION_DETECTED_EVENT_TYPE = "deviation_detected"

EXECUTION_TRACKING_ACTOR = "execution-tracking-service"

# 편차/에스컬레이션 알림 배너(ARCHITECTURE.md §7.1 "실행 추적" 화면)가 나머지
# 일반 이벤트와 구분해 강조할 수 있도록, 이 모듈과 오케스트레이션 모듈이 남기는
# 이벤트 타입을 한 곳에 모아둔다. 문자열 이름 자체에 의존하지 않고 프론트가
# `is_deviation_event` 불리언 하나만 보고 배너를 띄울 수 있게 하기 위함.
DEVIATION_EVENT_TYPES: frozenset[str] = frozenset(
    {
        DEVIATION_DETECTED_EVENT_TYPE,
        "deviation_triggered_reevaluation",  # app.services.orchestration.handle_execution_deviation
        "deadline_overrun_escalated",  # app.services.orchestration.check_deadline_overrun
    }
)

# "기한 내 미수락" 판단의 폴백 임계값 -- decision_package가 아직 없어
# recommended_deadline을 기준으로 삼을 수 없는 드문 경우에만 쓰인다. SOP 메시지
# 자체가 요구하는 절차(app/services/communication.py의 acknowledgment_method:
# "수신 확인 후 회신")를 감안해, 정상 업무 시간 기준 합리적인 응답 대기시간으로
# 4시간을 채택한다 -- 실시간 외부 시스템이 없어 더 정교한 값을 계산할 근거가
# 없으므로, 이 상수 자체가 이번 스코프의 판단값임을 코드 주석으로 명시한다.
FALLBACK_ACCEPTANCE_WINDOW = timedelta(hours=4)


class SopNotFoundError(LookupError):
    """`sop_id`(=원래 `sop_dispatched` audit_log 행의 id)가 존재하지 않거나,
    그 id의 audit_log 행이 애초에 `sop_dispatched` 행이 아니다. API 계층이
    404로 변환한다."""


class InvalidSopStatusError(ValueError):
    """status가 VALID_SOP_STATUSES 중 하나가 아니다. API 계층이 400으로
    변환한다."""


def _as_aware_utc(value: datetime) -> datetime:
    """orchestration.py의 동명 헬퍼와 동일한 이유 -- Postgres TIMESTAMPTZ가
    일부 드라이버 설정에서 naive datetime으로 돌아올 수 있어, 비교 전에 항상
    aware UTC로 정규화한다."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# ------------------------------------------------------------------
# 상태 전이 기록 -- PATCH /sop/{sop_id}/status
# ------------------------------------------------------------------


def record_status_transition(
    db: Session, sop_id: int, status: str, actor: str, note: str | None = None
) -> AuditLog:
    """PATCH /sop/{sop_id}/status의 서비스 로직. 필드 하나를 덮어쓰지 않고,
    `audit_log`에 새 행을 append한다 -- 이력이 항상 남아야 한다는 페르소나
    문서의 요구사항.

    가드:
      - `sop_id`가 실제 존재하는 `sop_dispatched` audit_log 행이어야 한다
        (아니면 SopNotFoundError -> API 404).
      - `status`가 VALID_SOP_STATUSES 중 하나여야 한다(아니면
        InvalidSopStatusError -> API 400). GET /incidents/{id}/sop-status가
        `수신`/`수락`/`완료`/`실패` 문자열을 그대로 인지해 편의 필드를 채우므로
        (app/services/communication.py), 이 문자열들과 정확히 일치시킨다."""

    if status not in VALID_SOP_STATUSES:
        raise InvalidSopStatusError(
            f"status must be one of {VALID_SOP_STATUSES}, got {status!r}"
        )

    audit_repo = AuditLogRepository(db)
    dispatch_row = audit_repo.get(sop_id)
    if dispatch_row is None or dispatch_row.event_type != SOP_DISPATCH_EVENT_TYPE:
        raise SopNotFoundError(
            f"sop {sop_id} not found -- no {SOP_DISPATCH_EVENT_TYPE!r} audit_log row with this id"
        )

    return audit_repo.add(
        incident_id=dispatch_row.incident_id,
        event_type=STATUS_TRANSITION_EVENT_TYPE,
        actor=actor,
        reason=note,
        payload={"sop_id": sop_id, "status": status, "note": note},
    )


# ------------------------------------------------------------------
# 편차 감지 -- 순수 함수, DB에 아무것도 쓰지 않는다.
# ------------------------------------------------------------------


@dataclass(frozen=True)
class DeviationResult:
    """detect_deviation의 반환값 -- 사유와 관련 sop_id 목록, 카테고리별 상세."""

    reason: str
    related_sop_ids: list[int] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)


def detect_deviation(db: Session, incident_id: int) -> DeviationResult | None:
    """계획값(decision_package.recommended_deadline)과 실제 SOP 상태 이력을
    비교하는 순수 함수(DB에 쓰지 않음) -- 편차가 있으면 DeviationResult, 없으면
    None을 반환한다.

    이번 스코프에서 실제로 계산 가능한 편차 2가지만 구현한다
    (simulation-supply-chain-tool.md §6.3, 실시간 외부 시스템이 없어 판단
    가능한 것만):

      1. 기한 내 미수락 -- SOP가 발송됐는데 결정기한(decision_package.
         recommended_deadline)이 지나도록(또는 결정기한 자체가 없다면
         FALLBACK_ACCEPTANCE_WINDOW가 지나도록) '수락' 상태 이벤트가 없음.
      2. 계획보다 지연된 완료 -- 결정기한이 지났는데 아직 '완료' 상태에
         이르지 못함(수락 여부와 무관 -- 수락은 했지만 시작/진행에 머물러
         있는 경우도 포함).

    이번 스코프에서 판단 불가능한 조건(§6.3의 나머지 3개, 정직하게 스코프
    밖으로 문서화 -- 억지로 구현하지 않음):
      - 운송·재고·생산 상태가 예상 범위를 벗어남: TMS/WMS/MES 등 실시간
        운영 시스템 연동이 이 스코프에 없어(ARCHITECTURE.md §6) 비교할 "실제
        운영 상태" 데이터 자체가 없다.
      - 확보한 자원이 취소되거나 다른 사건과 충돌함: 자원 예약/확정을 관리하는
        별도 테이블/시스템이 이 코드베이스에 없다(app/services/communication.py
        모듈 docstring 참고 -- incidents.status='승인'을 자원확정 신호로 대신
        쓰는 것이 이번 스코프의 전부).
      - 새로운 사건이나 영향 대상이 발견됨: 사건 탐지 자체는 incident-intake
        에이전트의 책임이고, 이 함수가 사후적으로 "새 사건이 발견됐다"고
        판단할 근거 데이터(예: 사건 간 연관관계 필드)가 없다.
    """

    if IncidentRepository(db).get(incident_id) is None:
        return None

    try:
        statuses = sop_status_for_incident(db, incident_id)
    except IncidentNotFoundError:
        return None

    if not statuses:
        return None

    latest_package = DecisionPackageRepository(db).latest_for_incident(incident_id)
    deadline: datetime | None = None
    if latest_package is not None and latest_package.recommended_deadline is not None:
        deadline = _as_aware_utc(latest_package.recommended_deadline)

    now = datetime.now(timezone.utc)

    unaccepted_overdue: list[int] = []
    incomplete_overdue: list[int] = []

    for item in statuses:
        if item["status"] == COMPLETED_STATUS:
            continue  # 계획대로(또는 늦더라도) 이미 완료 -- 더 이상 편차 아님

        accepted = item["accepted_at"] is not None

        if deadline is not None and now > deadline:
            if not accepted:
                unaccepted_overdue.append(item["sop_id"])
            else:
                incomplete_overdue.append(item["sop_id"])
        elif deadline is None and not accepted:
            dispatched_at = _as_aware_utc(item["dispatched_at"])
            if now - dispatched_at > FALLBACK_ACCEPTANCE_WINDOW:
                unaccepted_overdue.append(item["sop_id"])

    if not unaccepted_overdue and not incomplete_overdue:
        return None

    deadline_text = deadline.isoformat() if deadline is not None else f"발송 후 {FALLBACK_ACCEPTANCE_WINDOW}(결정기한 없음)"

    reason_parts: list[str] = []
    if unaccepted_overdue:
        reason_parts.append(
            f"기한 내 미수락 -- 결정기한({deadline_text}) 경과에도 수락되지 않은 SOP {len(unaccepted_overdue)}건: {unaccepted_overdue}"
        )
    if incomplete_overdue:
        reason_parts.append(
            f"계획보다 지연된 완료 -- 결정기한({deadline_text}) 경과에도 완료되지 않은 SOP {len(incomplete_overdue)}건: {incomplete_overdue}"
        )

    related_sop_ids = sorted(set(unaccepted_overdue) | set(incomplete_overdue))

    return DeviationResult(
        reason=" / ".join(reason_parts),
        related_sop_ids=related_sop_ids,
        detail={
            "unaccepted_overdue_sop_ids": unaccepted_overdue,
            "incomplete_overdue_sop_ids": incomplete_overdue,
            "recommended_deadline": deadline.isoformat() if deadline is not None else None,
        },
    )


# ------------------------------------------------------------------
# 편차 감지 -> 오케스트레이션 위임
# ------------------------------------------------------------------


async def check_and_handle_deviation(
    db: Session,
    incident_id: int,
    llm_provider: LLMProvider | None = None,
    *,
    additional_reason: str | None = None,
) -> dict[str, Any] | None:
    """detect_deviation()으로 편차를 감지하면(또는 호출부가 이미 편차로 확정한
    별도 사유가 있으면) `app.services.orchestration.handle_execution_deviation`
    에 위임한다. **이 함수는 절대 직접 ensure_snapshot_and_dag/
    validate_candidates/simulate_candidates를 호출하지 않는다** -- 오케스트레이션
    함수를 거치는 것이 유일한 재계산 경로다(agents/execution-tracking.md 정체성:
    "문제를 스스로 해결하려 하지 않는다").

    `additional_reason`: PATCH /sop/{sop_id}/status가 방금 기록한 상태 전이가
    그 자체로 편차인 경우(예: status='실패' -- 자원 취소/충돌에 준하는 실행
    실패) detect_deviation의 시간 기반 조건과 무관하게 즉시 재평가를 위임하기
    위한 훅. 이 값이 주어지면 detect_deviation이 아무것도 찾지 못해도 그 사유
    만으로 위임한다.

    편차가 없고 additional_reason도 없으면 None을 반환한다(아무것도 하지
    않음). 편차 감지 자체도 `audit_log`에 `event_type='deviation_detected'`로
    기록한 뒤 위임한다."""

    deviation = detect_deviation(db, incident_id)

    if deviation is None and additional_reason is None:
        return None

    reasons: list[str] = []
    related_sop_ids: list[int] = []
    detail: dict[str, Any] = {}

    if deviation is not None:
        reasons.append(deviation.reason)
        related_sop_ids.extend(deviation.related_sop_ids)
        detail.update(deviation.detail)
    if additional_reason is not None:
        reasons.append(additional_reason)

    combined_reason = " / ".join(reasons)

    AuditLogRepository(db).add(
        incident_id=incident_id,
        event_type=DEVIATION_DETECTED_EVENT_TYPE,
        actor=EXECUTION_TRACKING_ACTOR,
        reason=combined_reason,
        payload={"related_sop_ids": related_sop_ids, "detail": detail},
    )

    logger.info(
        "Deviation detected for incident %s -- delegating re-evaluation to orchestration: %s",
        incident_id,
        combined_reason,
    )

    return await handle_execution_deviation(db, incident_id, combined_reason, llm_provider)


# ------------------------------------------------------------------
# GET /incidents/{id}/timeline
# ------------------------------------------------------------------


def timeline_for_incident(db: Session, incident_id: int) -> list[dict[str, Any]]:
    """GET /incidents/{id}/timeline의 서비스 로직 -- AuditLogRepository.
    timeline_for_incident의 원본 행들을 프론트의 타임라인 뷰 + 편차/에스컬레이션
    알림 배너(ARCHITECTURE.md §7.1)가 그대로 쓸 수 있는 시간순 배열로 변환한다.

    `is_deviation_event`는 DEVIATION_EVENT_TYPES에 속하는 event_type인지를
    미리 판별해주는 편의 필드다 -- 프론트가 문자열 목록을 직접 하드코딩하지
    않고 이 불리언 하나만 보고 배너를 띄울지 결정할 수 있다."""

    if IncidentRepository(db).get(incident_id) is None:
        raise IncidentNotFoundError(f"incident {incident_id} not found")

    rows = AuditLogRepository(db).timeline_for_incident(incident_id)

    events: list[dict[str, Any]] = []
    for row in rows:
        payload = row.payload or {}
        events.append(
            {
                "id": row.id,
                "event_type": row.event_type,
                "actor": row.actor,
                "reason": row.reason,
                "sop_id": payload.get("sop_id"),
                "status": payload.get("status"),
                "payload": payload,
                "created_at": row.created_at,
                "is_deviation_event": row.event_type in DEVIATION_EVENT_TYPES,
            }
        )

    return events
