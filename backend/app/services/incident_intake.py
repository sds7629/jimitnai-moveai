"""Core incident-intake logic (agents/incident-intake.md).

This is the entry point of the whole workflow (simulation-supply-chain-tool.md
§2, §3.1): before any downstream analysis (Impact DAG, simulation, etc.) an
incoming incident report must be checked for duplication, false positives,
and missing required data. This module owns that gate.

Two hard rules from the persona doc, enforced here:
  1. Duplicate/false-positive/status-transition decisions must always be
     recorded to audit_log with a reason — no silent auto-classification.
  2. Missing input that cannot be backfilled must become an explicit
     ASSUMPTION string, never be dropped silently.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.incident import Incident
from app.repositories.audit_log import AuditLogRepository
from app.repositories.incidents import IncidentRepository
from app.schemas.incident import AFFECTED_TARGET_KEYS, IncidentCreate

# "발생시각 근접 범위" (simulation-supply-chain-tool.md §3.1) names the check
# but not a number. ASSUMPTION: 12 hours is used as the proximity window —
# wide enough to catch re-reports of the same disruption (e.g. a second
# operator submitting the same port congestion a few hours later) without
# conflating two genuinely distinct incidents of the same type at the same
# location on different days. This is a system parameter, not user input;
# it is documented here rather than added to incidents.assumptions.
DUPLICATE_DETECTION_WINDOW = timedelta(hours=12)

# Automation acts as its own audit actor for decisions this service makes
# without a human in the loop (duplicate detection, initial classification).
# Human-triggered actions (dismiss/close) carry the caller-supplied actor
# instead — see dismiss_incident() below.
AUTOMATION_ACTOR = "incident-intake-service"

DISMISS_STATUSES: tuple[str, ...] = ("오탐", "종료")


class IncidentIntakeResult:
    """Return value of create_incident() — bundles the persisted row with
    the request-time-only bookkeeping (missing_fields, duplicate_detected)
    that the API layer echoes back to the caller."""

    def __init__(self, incident: Incident, missing_fields: list[str], duplicate_detected: bool):
        self.incident = incident
        self.missing_fields = missing_fields
        self.duplicate_detected = duplicate_detected


def _resolve_missing_fields_and_assumptions(
    payload: IncidentCreate,
) -> tuple[list[str], list[str], dict]:
    """§3.1: '영향 가능 화물·부품·생산오더·고객'의 누락 여부를 확인한다.

    이번 스코프에는 이 값을 자동으로 보완할 외부 조회원이 없다(ARCHITECTURE.md
    §6 — 실시간 외부 시스템 연동 제외). 따라서 보완 가능한 데이터 조회 단계는
    스킵되고, 누락값은 전부 명시적 ASSUMPTION 문자열로 남는다. 침묵 처리(그냥
    빈 값으로 저장)는 금지.

    Returns (missing_fields, assumptions, affected_targets_dict).
    """

    missing_fields: list[str] = []
    assumptions: list[str] = []

    if payload.affected_targets is None:
        missing_fields.append("affected_targets")
        assumptions.append(
            "ASSUMPTION: 영향 가능 화물/부품/생산오더/고객 정보가 전혀 입력되지 "
            "않아 영향 범위 미상으로 가정함 — 후속 조사로 보완 필요"
        )
        affected_targets_dict: dict = {}
    else:
        raw = payload.affected_targets.model_dump()
        affected_targets_dict = {k: v for k, v in raw.items() if v}
        for key in AFFECTED_TARGET_KEYS:
            value = raw.get(key)
            if not value:
                missing_fields.append(f"affected_targets.{key}")
                assumptions.append(
                    f"ASSUMPTION: affected_targets.{key} 미제공 — 해당 범주 영향 "
                    "대상 없음으로 가정함"
                )

    return missing_fields, assumptions, affected_targets_dict


def create_incident(db: Session, payload: IncidentCreate) -> IncidentIntakeResult:
    """Validates and classifies an incoming incident report.

    Flow (agents/incident-intake.md 작업 지침 #1-#4):
      1. Detect missing optional-but-expected fields -> assumptions.
      2. Duplicate check via IncidentRepository.find_open_duplicates
         (same type + location + occurred_at within DUPLICATE_DETECTION_WINDOW,
         excluding already-closed/dismissed incidents).
      3. Classify: duplicate candidates found -> status='중복' with
         duplicate_of_incident_id set; otherwise -> status='유효' (passed
         automated validation, matching the seed scenarios which are all
         seeded directly as '유효').
      4. Persist, then record the classification (and duplicate finding, if
         any) to audit_log with a reason — never a silent status.
    """

    incident_repo = IncidentRepository(db)
    audit_repo = AuditLogRepository(db)

    missing_fields, assumptions, affected_targets_dict = _resolve_missing_fields_and_assumptions(payload)

    duplicates = incident_repo.find_open_duplicates(
        payload.type, payload.location, payload.occurred_at, DUPLICATE_DETECTION_WINDOW
    )

    duplicate_detected = bool(duplicates)
    if duplicate_detected:
        primary = duplicates[0]
        status = "중복"
        duplicate_of_incident_id: int | None = primary.id
    else:
        status = "유효"
        duplicate_of_incident_id = None

    incident = incident_repo.add(
        type=payload.type,
        location=payload.location,
        occurred_at=payload.occurred_at,
        status=status,
        duplicate_of_incident_id=duplicate_of_incident_id,
        affected_targets=affected_targets_dict,
        assumptions=assumptions,
    )

    audit_repo.add(
        incident_id=incident.id,
        event_type="incident_created",
        actor=AUTOMATION_ACTOR,
        reason=(
            f"신규 사건 접수 — 중복 후보 없음, 자동 분류: {status}"
            if not duplicate_detected
            else f"신규 사건 접수 — 기존 사건 #{duplicate_of_incident_id}과 중복 가능성 확인, 자동 분류: {status}"
        ),
        payload={"status": status, "missing_fields": missing_fields},
    )

    if duplicate_detected:
        audit_repo.add(
            incident_id=incident.id,
            event_type="duplicate_detected",
            actor=AUTOMATION_ACTOR,
            reason=(
                f"동일 유형('{payload.type}') + 동일 위치('{payload.location}') + "
                f"발생시각 {DUPLICATE_DETECTION_WINDOW.total_seconds() / 3600:.0f}시간 "
                f"이내 근접 — 기존 미종료 사건 #{duplicate_of_incident_id}과 중복으로 판정"
            ),
            payload={
                "duplicate_of_incident_id": duplicate_of_incident_id,
                "candidate_incident_ids": [d.id for d in duplicates],
            },
        )

    return IncidentIntakeResult(
        incident=incident, missing_fields=missing_fields, duplicate_detected=duplicate_detected
    )


def dismiss_incident(
    db: Session,
    incident_id: int,
    reason: str,
    actor: str,
    new_status: str = "오탐",
) -> Incident | None:
    """Marks an incident 오탐 (false positive) or 종료 (closed).

    `reason` is required by the caller's schema (IncidentDismissRequest) and
    is always written to audit_log along with the previous status — this is
    the enforcement point for agents/incident-intake.md's "사유 없는 자동
    종료는 금지" rule. Returns None if the incident does not exist.
    """

    if new_status not in DISMISS_STATUSES:
        raise ValueError(f"unsupported dismiss status: {new_status!r}, must be one of {DISMISS_STATUSES}")
    if not reason or not reason.strip():
        raise ValueError("reason is required to dismiss/close an incident")

    incident_repo = IncidentRepository(db)
    existing = incident_repo.get(incident_id)
    if existing is None:
        return None

    previous_status = existing.status
    updated = incident_repo.update(incident_id, status=new_status)

    AuditLogRepository(db).add(
        incident_id=incident_id,
        event_type="false_positive_dismissed" if new_status == "오탐" else "incident_closed",
        actor=actor,
        reason=reason,
        payload={"previous_status": previous_status, "new_status": new_status},
    )

    return updated
