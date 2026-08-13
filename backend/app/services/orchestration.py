"""오케스트레이션 에이전트 (agents/orchestration.md).

Owns the one place where a 담당자's decision on an incident turns into the
next system action, and the one place a missed decision deadline turns into
a recorded escalation. Nothing here calculates numbers or searches
documents itself (persona doc: "스스로 숫자를 계산하거나 문서를 검색하지 않는다") --
it only decides *which* already-built service to call next and records the
decision trail in `approvals` (+ `audit_log`, mirroring the convention
app/services/incident_intake.py already established for incidents.status
transitions).

Five branches, one explicit state machine (agents/orchestration.md work
item #2: "암묵적 흐름을 만들지 않는다") -- `process_approval` dispatches via an
explicit if/elif chain with a final `else` that raises, never a dict lookup
with a silent default:

  승인       -> incidents.status='승인'. "실행 자원 확정"과 "SOP 배포" are the
                communication-sop wave's job (not built yet, per the task
                brief) -- this status transition on its own *is* the signal
                that wave watches for (agents/orchestration.md 의존관계:
                "커뮤니케이션 에이전트(승인 시 SOP 배포 트리거)").
  조건부승인  -> the exact same incidents.status='승인' transition.
                db/init/002-schema.sql's CHECK constraint on incidents.status
                has no separate "조건부승인" state -- approvals.decision_type
                is what distinguishes it, not a different incident status.
                The condition itself must be a real sentence, not a blank
                rubber-stamp -- enforced at the schema layer
                (app/schemas/approval.py's CONDITIONAL_APPROVAL_MIN_REASON_LENGTH),
                one layer on top of the DB's plain NOT NULL.
  수정요청    -> incidents.status='처리중' + re-run constraint-validation and
                simulation against the *existing* response_candidates (see
                _request_revision's docstring for why this stops short of a
                full "regenerate candidates" step).
  반려       -> incidents.status stays '처리중' (see _reject's docstring for
                why no automatic replacement-candidate logic is built here).
  기한초과   -> never accepted from a client through `process_approval` --
                see check_deadline_overrun below, the system-only path.

Every branch appends one `approvals` row (decided_at/approver/reason/
data_version_ref/scenario_version_ref, auto-filled from the incident's
*latest* operational_snapshots row -- "당시 데이터·시나리오 버전을 감사로그에
남긴다", simulation-supply-chain-tool.md §5.2) and one `audit_log` row,
matching the pattern app/services/incident_intake.py already uses for
incidents.status changes.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.llm import LLMProvider
from app.models.approval import Approval
from app.repositories.approvals import ApprovalRepository
from app.repositories.audit_log import AuditLogRepository
from app.repositories.decision_packages import DecisionPackageRepository
from app.repositories.incidents import IncidentRepository
from app.repositories.operational_snapshots import OperationalSnapshotRepository
from app.services.constraint_validation import validate_candidates
from app.services.operational_graph import IncidentNotFoundError, ensure_snapshot_and_dag  # noqa: F401 -- IncidentNotFoundError re-exported for API layer convenience
from app.services.simulation import SimulationValidationError, simulate_candidates

__all__ = [
    "process_approval",
    "check_deadline_overrun",
    "handle_execution_deviation",
    "IncidentNotFoundError",
    "UnknownDecisionTypeError",
    "CLIENT_DECISION_TYPES",
    "APPROVED_STATUS",
    "IN_PROGRESS_STATUS",
]

# Mirrors db/init/002-schema.sql's CHECK constraint on approvals.decision_type.
ALL_DECISION_TYPES: tuple[str, ...] = ("승인", "조건부승인", "수정요청", "반려", "기한초과")

# '기한초과' is deliberately excluded here -- it can only ever be produced by
# check_deadline_overrun() below, never by a client calling process_approval
# directly (agents/orchestration.md work item #5 / persona doc §5.2's last
# branch: "시스템이 감지"). app/schemas/approval.py enforces the same
# restriction one layer up, at the request-body level; this tuple is the
# defense-in-depth check inside the service itself, so a caller that bypasses
# the API schema (e.g. a future internal caller) still cannot inject one.
CLIENT_DECISION_TYPES: tuple[str, ...] = ("승인", "조건부승인", "수정요청", "반려")

# incidents.status values this module transitions into. There is no separate
# '조건부승인' incident status -- see module docstring.
APPROVED_STATUS = "승인"
IN_PROGRESS_STATUS = "처리중"

SYSTEM_ACTOR = "system"
ORCHESTRATION_ACTOR = "orchestration-service"


class UnknownDecisionTypeError(ValueError):
    """`decision_type` is not one of CLIENT_DECISION_TYPES. Should be
    unreachable through the API (app/schemas/approval.py rejects it first),
    but process_approval re-checks it anyway -- an explicit branch table
    must never have a silent fallthrough for an unrecognized value."""


def _as_aware_utc(value: datetime) -> datetime:
    """Postgres TIMESTAMPTZ columns round-trip through psycopg as naive
    datetimes when the session/driver has no explicit tzinfo attached in
    some configurations -- normalize everything to aware UTC before
    comparing across approvals.decided_at / decision_packages.created_at /
    decision_packages.recommended_deadline so a naive-vs-aware comparison
    never raises TypeError."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _latest_version_refs(db: Session, incident_id: int) -> tuple[str | None, str | None]:
    """(data_version_ref, scenario_version_ref) from the incident's latest
    operational_snapshots row, or (None, None) if no snapshot exists yet
    (e.g. an approval decision made before the incident ever reached
    operational-graph/simulate -- unusual, but not an error condition this
    module should block on)."""

    snapshot = OperationalSnapshotRepository(db).latest_for_incident(incident_id)
    if snapshot is None:
        return None, None
    return snapshot.data_version, snapshot.scenario_version


def _record_decision_and_transition(
    db: Session,
    incident_id: int,
    *,
    decision_type: str,
    reason: str,
    approver: str,
    data_version_ref: str | None,
    scenario_version_ref: str | None,
    new_status: str,
    audit_event_type: str,
    audit_reason: str,
) -> Approval:
    """Shared tail end of every branch below: append one `approvals` row,
    transition `incidents.status` (idempotent -- always applied, even if it
    happens to match the current value), and append one `audit_log` row.
    Never called directly from outside this module -- each branch function
    below is the one place that decides `new_status`/event_type/reason for
    its own decision_type, so the state machine stays a set of explicit,
    named functions rather than one generic call with implicit meaning."""

    approval = ApprovalRepository(db).add(
        incident_id=incident_id,
        decision_type=decision_type,
        reason=reason,
        approver=approver,
        data_version_ref=data_version_ref,
        scenario_version_ref=scenario_version_ref,
    )

    IncidentRepository(db).update(incident_id, status=new_status)

    AuditLogRepository(db).add(
        incident_id=incident_id,
        event_type=audit_event_type,
        actor=approver,
        reason=audit_reason,
        payload={
            "decision_type": decision_type,
            "new_status": new_status,
            "data_version_ref": data_version_ref,
            "scenario_version_ref": scenario_version_ref,
        },
    )

    return approval


def _approve(
    db: Session, incident_id: int, reason: str, approver: str,
    data_version_ref: str | None, scenario_version_ref: str | None,
) -> Approval:
    """승인 -- incidents.status='승인'. Execution-resource confirmation and
    role-based SOP dispatch (simulation-supply-chain-tool.md §6) are owned by
    a wave that does not exist yet in this codebase; this status transition
    on its own is the entry signal that wave is expected to watch for, per
    the task brief -- no dispatch/reservation logic is built here."""

    return _record_decision_and_transition(
        db, incident_id,
        decision_type="승인",
        reason=reason,
        approver=approver,
        data_version_ref=data_version_ref,
        scenario_version_ref=scenario_version_ref,
        new_status=APPROVED_STATUS,
        audit_event_type="incident_approved",
        audit_reason=f"담당자 승인 -- {reason}",
    )


def _conditional_approve(
    db: Session, incident_id: int, reason: str, approver: str,
    data_version_ref: str | None, scenario_version_ref: str | None,
) -> Approval:
    """조건부승인 -- the same incidents.status='승인' transition as 승인 (see
    module docstring for why there is no separate incident status). What
    distinguishes it is entirely carried in approvals.decision_type +
    approvals.reason (the condition text) -- the next wave (communication-sop)
    is expected to read decision_type='조건부승인' and fold `reason` into the
    SOP/실행계획 it dispatches, per simulation-supply-chain-tool.md §5.2
    ("승인 조건을 반영해 실행계획과 시나리오 버전 갱신"). That reflection step
    itself belongs to that wave, not this one."""

    return _record_decision_and_transition(
        db, incident_id,
        decision_type="조건부승인",
        reason=reason,
        approver=approver,
        data_version_ref=data_version_ref,
        scenario_version_ref=scenario_version_ref,
        new_status=APPROVED_STATUS,
        audit_event_type="incident_conditionally_approved",
        audit_reason=f"담당자 조건부승인 -- {reason}",
    )


async def _request_revision(
    db: Session, incident_id: int, reason: str, approver: str,
    data_version_ref: str | None, scenario_version_ref: str | None,
    llm_provider: LLMProvider | None,
) -> Approval:
    """수정요청 -- incidents.status='처리중' 복귀 + 제약 재검증과 재시뮬레이션을
    다시 실행한다.

    판단 근거(스코프 결정, 코드 주석으로 남김): "대응안 생성부터 다시" 트리거하는
    가장 좁은 해석은 response-design(generate_candidates)까지 다시 부르는
    것이겠지만, 그러면 완전히 새로운 response_candidates 세트가 기존 세트 옆에
    추가되어 "담당자가 반려/수정한 후보가 무엇이었는지"를 흐리게 만든다.
    수정요청은 Wave 3(response-design/simulation)의 "재실행 정책"과는 다른
    성격의 사용자 의도다 -- 담당자가 "이 조건으로 다시 검토해달라"는 것이지
    "완전히 새 후보를 보여달라"는 것이 아니다. 따라서 여기서는 기존
    response_candidates를 그대로 유지한 채 validate_candidates(제약 재검증,
    response_candidates를 in-place로 갱신) + simulate_candidates(재시뮬레이션,
    simulation_results에 append-only로 새 행 추가)만 다시 돌린다. 완전히 새로운
    후보 세트를 만드는 "재생성" 자체는 이번 스코프에서는 과설계로 판단했다 --
    필요해지면 response-design 웨이브가 담당자의 수정 요청 사유(reason)를 받아
    후보를 실제로 바꿔 만드는 전용 로직을 추가하는 것이 맞다.

    이 재실행 이후 담당자가 GET /incidents/{id}/decision-package를 다시 호출하면
    그 엔드포인트의 기존 재계산 정책(app/api/decision_package.py -- 최신
    simulation_results가 기존 패키지보다 새 것이면 재계산)에 따라 갱신된
    decision_packages 행이 자동으로 만들어진다. 이 함수는 decision_package를
    직접 다시 만들지 않는다 -- "재계산"은 response-optimization 웨이브의
    책임 경계를 그대로 존중한다.

    SimulationValidationError / LLMConfigError는 그대로 위로 전파한다(API
    계층이 502/503으로 변환) -- 재시뮬레이션이 실패했는데 수정요청 자체는
    성공한 것처럼 보이면 담당자가 다음 결정을 잘못된 전제로 내릴 수 있다."""

    approval = _record_decision_and_transition(
        db, incident_id,
        decision_type="수정요청",
        reason=reason,
        approver=approver,
        data_version_ref=data_version_ref,
        scenario_version_ref=scenario_version_ref,
        new_status=IN_PROGRESS_STATUS,
        audit_event_type="incident_revision_requested",
        audit_reason=f"담당자 수정요청 -- {reason}",
    )

    validate_candidates(db, incident_id)
    await simulate_candidates(db, incident_id, llm_provider)

    AuditLogRepository(db).add(
        incident_id=incident_id,
        event_type="revision_reevaluated",
        actor=ORCHESTRATION_ACTOR,
        reason="수정요청에 따라 기존 대응안(response_candidates)을 유지한 채 제약 재검증 + 재시뮬레이션 실행",
        payload={"reason": reason},
    )

    return approval


def _reject(
    db: Session, incident_id: int, reason: str, approver: str,
    data_version_ref: str | None, scenario_version_ref: str | None,
) -> Approval:
    """반려 -- incidents.status는 '처리중'으로 유지(이미 '처리중'이 아니었다면
    되돌림)하고, 반려 사유만 append-only로 기록한다.

    판단 근거(스코프 결정, 코드 주석으로 남김): 업무 명세 §5.2는 반려 시 "대체
    대응안 생성"을 요구하지만, "반려된 후보와 다른 대체안을 자동으로 골라
    만든다"에는 (a) 어떤 후보가 반려 대상이었는지를 candidate 단위로 추적하는
    필드가 response_candidates에 아직 없고, (b) response-design 웨이브가 "이미
    반려된 후보는 제외하고 생성하라"는 신호를 받는 인터페이스도 없다. 이 두
    전제 없이 "자동 재생성"을 흉내 내면 실제로는 그냥 같은 후보 집합을 다시
    보여주는 것과 다르지 않으므로, 이번 스코프에서는 다음까지만 한다:
      1. 반려 결정/사유를 approvals에 기록.
      2. incidents.status='처리중' 유지 -- 담당자가 다시 검토할 수 있는 상태로
         되돌린다(승인/조건부승인 상태로 잘못 넘어가지 않도록).
      3. 담당자가 이후 다시 POST /incidents/{id}/simulate를 호출하면 기존
         파이프라인이 그대로 열려 있어 재검토가 가능하다 -- response-design
         웨이브가 "반려된 후보 제외" 로직을 갖추게 되면 그 때 이 함수가 그
         신호를 넘겨주도록 확장하면 된다.
    "대체 대응안 자동 생성" 자체는 이후 웨이브(response-design이 후보별 반려
    이력을 인지할 수 있게 된 다음)에서 구현하는 것이 맞다고 판단했다.

    알려진 한계(교차 웨이브 간극, 정직하게 문서화): incidents.status='처리중'
    으로 되돌리는 순간, operational-graph 웨이브가 이미 소유한 적격성 게이트
    (app/services/operational_graph.py의 ensure_snapshot_and_dag -- status가
    '유효'인 사건만 스냅샷/파이프라인 대상)에 걸려, 실제로 POST
    /incidents/{id}/simulate를 다시 호출하면 지금은 409가 반환된다(위 3번의
    "인터페이스가 열려 있다"는 것은 "orchestration이 추가로 막지 않는다"는
    의미이지, "지금 당장 재호출이 성공한다"는 뜻이 아니다 -- 실제 성공하려면
    (a) incidents.status를 다시 '유효'로 되돌리는 전이를 어느 웨이브가 추가로
    만들거나, (b) _request_revision처럼 상태와 무관하게 동작하는 재검증/
    재시뮬레이션 경로를 반려에도 적용해야 한다. 둘 다 이번 스코프 판단으로는
    아직 이르다고 보고(반려 후보 추적 로직이 없는 채로 그 경로를 여는 것은
    의미 없는 재실행일 뿐) 구현하지 않았다 -- 이 한계는 tests/test_orchestration.py
    의 반려 테스트에서 실제 409 응답으로 확인된다."""

    return _record_decision_and_transition(
        db, incident_id,
        decision_type="반려",
        reason=reason,
        approver=approver,
        data_version_ref=data_version_ref,
        scenario_version_ref=scenario_version_ref,
        new_status=IN_PROGRESS_STATUS,
        audit_event_type="incident_rejected",
        audit_reason=f"담당자 반려 -- {reason}",
    )


async def process_approval(
    db: Session,
    incident_id: int,
    decision_type: str,
    reason: str,
    approver: str,
    llm_provider: LLMProvider | None = None,
) -> Approval:
    """Entry point for POST /incidents/{id}/approvals. Explicit state
    machine over the 4 client-triggerable decision types (agents/
    orchestration.md work item #2) -- '기한초과' is handled exclusively by
    check_deadline_overrun() below and is rejected here even if somehow
    passed in (see UnknownDecisionTypeError / CLIENT_DECISION_TYPES).

    `async def` only because the 수정요청 branch awaits simulate_candidates's
    LLM calls (CLAUDE.md 비동기 처리 원칙) -- the other three branches are
    plain synchronous DB work under the hood; the whole function is async
    because *any* of its callable branches might need to await, not because
    every branch does.

    Raises IncidentNotFoundError (404), UnknownDecisionTypeError (400),
    SimulationValidationError / LLMConfigError (502/503, 수정요청 branch
    only) -- the API layer (app/api/approvals.py) translates each."""

    incident = IncidentRepository(db).get(incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"incident {incident_id} not found")

    data_version_ref, scenario_version_ref = _latest_version_refs(db, incident_id)

    if decision_type == "승인":
        return _approve(db, incident_id, reason, approver, data_version_ref, scenario_version_ref)
    elif decision_type == "조건부승인":
        return _conditional_approve(db, incident_id, reason, approver, data_version_ref, scenario_version_ref)
    elif decision_type == "수정요청":
        return await _request_revision(
            db, incident_id, reason, approver, data_version_ref, scenario_version_ref, llm_provider
        )
    elif decision_type == "반려":
        return _reject(db, incident_id, reason, approver, data_version_ref, scenario_version_ref)
    else:
        # Covers both '기한초과' (system-only, see check_deadline_overrun) and
        # any genuinely unrecognized value -- neither gets a silent default.
        raise UnknownDecisionTypeError(
            f"decision_type {decision_type!r}은(는) 담당자가 직접 제출할 수 없습니다 "
            f"(허용값: {CLIENT_DECISION_TYPES})"
        )


def check_deadline_overrun(db: Session, incident_id: int) -> bool:
    """결정기한 초과 감지 (agents/orchestration.md work item #5) -- 폴링
    스케줄러가 아니라, 이 함수를 호출하는 두 지점(SSE 스트림 루프의 매 tick,
    GET /incidents/{id}/decision-package 요청 시점)에서 "지금 시각과 저장된
    기한을 비교"하는 방식으로 구현한다. 실제 알림 발송은 만들지 않는다
    (ARCHITECTURE.md §6 스코프 제외) -- 에스컬레이션은 approvals(+audit_log)에
    "기록"만 한다.

    Returns True only when *this call* just newly recorded a 기한초과
    escalation (i.e. observable state changed) -- callers (SSE loop) use this
    to decide whether to push a `deadline_overrun` event. False covers every
    other case (incident missing, no decision package yet, deadline not yet
    reached, or a decision/escalation already exists for the current
    decision package) -- calling this repeatedly is always safe/idempotent,
    never double-escalates for the same package.

    "아직 결정이 없으면"의 기준: 가장 최근 decision_package가 만들어진 *이후에*
    approvals에 어떤 결정(승인/조건부승인/수정요청/반려/기한초과)이라도 이미
    기록되어 있으면 이번 결정 사이클은 이미 처리된 것으로 보고 아무것도 하지
    않는다. 이렇게 최신 decision_package.created_at을 기준으로 삼는 이유는
    수정요청 이후 새 decision_package가 만들어지는 재사이클(§6.3 재계산)에서도
    "그 새 패키지에 대한 결정이 없었는가"를 다시 올바르게 판단하기 위해서다 --
    과거 사이클에서 이미 내려진 결정 때문에 새 사이클의 기한초과가 영원히
    가려지는 것을 막는다."""

    incident = IncidentRepository(db).get(incident_id)
    if incident is None:
        return False

    latest_package = DecisionPackageRepository(db).latest_for_incident(incident_id)
    if latest_package is None or latest_package.recommended_deadline is None:
        return False

    deadline = _as_aware_utc(latest_package.recommended_deadline)
    now = datetime.now(timezone.utc)
    if now <= deadline:
        return False  # not yet overdue

    package_created_at = _as_aware_utc(latest_package.created_at)
    existing_decisions = ApprovalRepository(db).for_incident(incident_id)
    for decision in existing_decisions:
        if _as_aware_utc(decision.decided_at) >= package_created_at:
            return False  # this decision cycle is already resolved

    data_version_ref, scenario_version_ref = _latest_version_refs(db, incident_id)

    ApprovalRepository(db).add(
        incident_id=incident_id,
        decision_type="기한초과",
        reason=(
            f"권고 결정기한({deadline.isoformat()}) 초과 -- 담당자 결정 없음. "
            "상위 책임자 에스컬레이션을 기록함(실제 알림 발송은 스코프 밖, ARCHITECTURE.md §6)."
        ),
        approver=SYSTEM_ACTOR,
        data_version_ref=data_version_ref,
        scenario_version_ref=scenario_version_ref,
    )

    AuditLogRepository(db).add(
        incident_id=incident_id,
        event_type="deadline_overrun_escalated",
        actor=SYSTEM_ACTOR,
        reason="결정기한 초과 -- 상위 책임자 에스컬레이션 기록(실제 알림 발송 없음, ARCHITECTURE.md §6)",
        payload={
            "recommended_deadline": deadline.isoformat(),
            "decision_package_id": latest_package.id,
        },
    )

    return True


async def handle_execution_deviation(
    db: Session,
    incident_id: int,
    deviation_reason: str,
    llm_provider: LLMProvider | None = None,
) -> dict:
    """편차(계획 대비 실행 이탈) 감지 시 재평가하는 진입점 -- execution-tracking
    웨이브(agents/execution-tracking.md)가 편차를 감지하면 이 함수 하나만
    호출한다. "재시뮬레이션 트리거는 이 페르소나(오케스트레이션)만 발생시킨다"
    (agents/orchestration.md) -- execution-tracking은 신호만 만들고 DAG나
    시뮬레이션 결과를 절대 직접 갱신하지 않는다.

    수행 순서 (simulation-supply-chain-tool.md §6.3):
      1. ensure_snapshot_and_dag(force_recompute=True)로 최신 데이터 기준
         Impact DAG를 재계산(append-only 새 snapshot/DAG 행).
      2. _request_revision과 동일한 판단 근거로 기존 response_candidates를
         그대로 유지한 채 validate_candidates(제약 재검증) +
         simulate_candidates(재시뮬레이션, append-only 새 simulation_results
         행)만 다시 돌린다 -- 완전 재생성은 이번 스코프에서도 여전히 과설계.
      3. 이미 incidents.status=='승인'(SOP 발송 전제조건)이었다면 '처리중'으로
         되돌린다 -- §6.3 마지막 문장("기존 승인 범위를 벗어나는 변경은 다시
         담당자 승인을 받는다")의 반영. 아직 승인 전('유효'/'처리중')이었다면
         그 상태를 그대로 유지한다.
      4. approvals에는 아무 행도 추가하지 않는다 -- 편차 감지는 담당자의
         승인/반려 결정이 아니라 시스템이 관찰한 사실이다. 대신 audit_log에
         event_type='deviation_triggered_reevaluation'으로 사유를 기록한다.

    병합 전 리뷰에서 발견/수정된 점: 이전 구현은 operational_graph의 게이트가
    '유효'만 허용한다는 이유로 재계산 직전에 status를 잠깐 '유효'로 돌렸다가
    직후 되돌리는 우회를 썼다. 이 방식은 각 상태 전이가 즉시 커밋되는
    리포지토리 구조(app/repositories/base.py)와 결합해 실제 문제를 만든다 --
    `await simulate_candidates(...)`로 이벤트 루프가 다른 요청에 양보하는 동안
    이 incident는 실제 DB에 커밋된 '유효' 상태로(원래는 '승인'/'처리중'인데도)
    잠시 노출되어, 동시에 들어온 다른 요청이 이 사건을 "아직 승인 전"으로
    잘못 관찰할 수 있었다. 그래서 이번 리뷰에서 대신 operational_graph.py의
    게이트 자체를 넓혔다(`RECOMPUTE_ELIGIBLE_STATUSES = ('유효','처리중','승인')`)
    -- '처리중'/'승인'은 애초에 '유효'를 한 번 거쳐야만 도달 가능한 후속
    상태이므로 재계산 대상에서 뺄 이유가 없었다. 이 함수는 이제 상태를 건드리지
    않고 곧바로 재계산을 호출한다(중간 상태 자체가 없어짐).

    Raises IncidentNotFoundError (호출부가 404로 변환), SimulationValidationError
    / LLMConfigError(재시뮬레이션 실패, 502/503) -- 그대로 위로 전파한다."""

    incident_repo = IncidentRepository(db)
    incident = incident_repo.get(incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"incident {incident_id} not found")

    previous_status = incident.status

    ensure_snapshot_and_dag(db, incident_id, force_recompute=True)
    validate_candidates(db, incident_id)
    await simulate_candidates(db, incident_id, llm_provider)

    reverted_to_in_progress = previous_status == APPROVED_STATUS
    final_status = IN_PROGRESS_STATUS if reverted_to_in_progress else previous_status
    incident_repo.update(incident_id, status=final_status)

    AuditLogRepository(db).add(
        incident_id=incident_id,
        event_type="deviation_triggered_reevaluation",
        actor=ORCHESTRATION_ACTOR,
        reason=deviation_reason,
        payload={
            "deviation_reason": deviation_reason,
            "previous_status": previous_status,
            "final_status": final_status,
            "reverted_to_in_progress": reverted_to_in_progress,
        },
    )

    return {
        "incident_id": incident_id,
        "dag_recomputed": True,
        "revalidated": True,
        "resimulated": True,
        "previous_status": previous_status,
        "final_status": final_status,
        "reverted_to_in_progress": reverted_to_in_progress,
        "deviation_reason": deviation_reason,
    }
