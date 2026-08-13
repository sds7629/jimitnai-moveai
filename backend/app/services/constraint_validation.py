"""제약 검증 에이전트 (agents/constraint-validation.md).

Stage 2 of the POST /incidents/{id}/simulate pipeline: takes the candidates
response-design produced (all validation_status='미검증') and classifies
each as 가능(executable) / 조건부(conditionally executable, with
preconditions) / 불가능(infeasible, with a required exclusion category +
detail). Baseline always passes as a special case -- 무대응 is always
executable by definition.

This stage is pure DB read/compare logic -- there is no LLM call and
therefore no blocking network I/O here, so (per explicit direction) it
stays a plain synchronous function; there is nothing to gain from making it
async.

Heuristic scope and limits (documented up front since this is intentionally
not a real reservation system):
  - Resource requirements are *inferred* from the candidate's free-text
    `description`/`preconditions` by scanning for the CTN-/PT-/PO- id
    conventions used throughout this codebase (see
    db/init/003-seed-scenarios.sql, app/services/operational_graph.py),
    not from a structured "required resources" field -- response_candidates
    has no such column and none was requested for this wave.
  - Transport-resource feasibility is judged against the *current*
    operational_snapshot for the candidate's own incident. A container in a
    "full stop" transport status (하역중단 -- e.g. the 파업 scenario, where
    nothing moves for anyone) makes any candidate that touches it
    infeasible; a "pending" status (반출대기/통관대기/하역중 -- normal
    processing delay, not a hard stop) makes it conditionally executable
    pending an explicit approval precondition.
  - Cross-incident resource-overlap check (agents/constraint-validation.md
    work item #2 / DoD): scans other *active* incidents' (status='유효')
    candidates that are already 가능/조건부 for an overlapping container id
    referenced in free text. This is a best-effort heuristic, not a real
    reservation ledger: (a) it only catches overlaps expressed as a shared
    CTN-... token in text, so a resource conflict described only in prose
    would be missed; (b) it is subject to a race/ordering effect -- if two
    incidents' candidates are validated concurrently before either is
    marked 가능/조건부, the overlap is not seen by either pass. A production
    system would need a real resource-allocation table instead.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.incident import Incident
from app.models.response_candidate import ResponseCandidate
from app.repositories.incidents import IncidentRepository
from app.repositories.operational_snapshots import OperationalSnapshotRepository
from app.repositories.response_candidates import ResponseCandidateRepository
from app.services.operational_graph import IncidentNotFoundError

__all__ = ["validate_candidates", "IncidentNotFoundError"]

ACTIVE_INCIDENT_STATUS = "유효"

BASELINE_CANDIDATE_TYPE = "baseline"

CONTAINER_ID_PATTERN = re.compile(r"CTN-[A-Za-z0-9\-]+")

# transport_state[container_id]['status'] values, per
# app/services/operational_graph.py's SCENARIO_TEMPLATES /
# db/init/003-seed-scenarios.sql seed rows.
FULL_STOP_TRANSPORT_STATUSES = {"하역중단"}
PENDING_TRANSPORT_STATUSES = {"반출대기", "통관대기", "하역중", "상태미상"}

TRANSPORT_KEYWORDS = ("컨테이너", "반출", "운송", "항만", "대체항", "긴급운송", "경로")
INVENTORY_KEYWORDS = ("대체 부품", "안전재고", "대체부품", "부품")

EXCLUSION_CATEGORIES = ("자원부족", "기한불가", "예산초과", "계약위반")


def _referenced_container_ids(candidate: ResponseCandidate, known_container_ids: list[str]) -> list[str]:
    text = f"{candidate.candidate_type} {candidate.description} " + " ".join(candidate.preconditions or [])
    found = set(CONTAINER_ID_PATTERN.findall(text))
    if found:
        matched_known = sorted(found & set(known_container_ids))
        return matched_known or sorted(found)
    if any(keyword in text for keyword in TRANSPORT_KEYWORDS):
        # Candidate clearly concerns transport/containers but didn't name a
        # specific one -- fall back to every container tracked in this
        # incident's own snapshot so the check still applies.
        return list(known_container_ids)
    return []


def _validate_transport_resource(
    candidate: ResponseCandidate, transport_state: dict, container_ids: list[str]
) -> tuple[str, str | None, str | None, list[str]] | None:
    if not container_ids:
        return None

    blocking = [
        cid for cid in container_ids if (transport_state.get(cid) or {}).get("status") in FULL_STOP_TRANSPORT_STATUSES
    ]
    if blocking:
        statuses = {(transport_state.get(cid) or {}).get("status") for cid in blocking}
        detail = (
            f"컨테이너 {', '.join(blocking)}가 '{', '.join(sorted(statuses))}' 상태로 "
            "운송 자원을 전혀 확보할 수 없음"
        )
        return "불가능", "자원부족", detail, []

    pending = [
        cid for cid in container_ids if (transport_state.get(cid) or {}).get("status") in PENDING_TRANSPORT_STATUSES
    ]
    if pending:
        preconditions = [f"컨테이너 {cid} 우선 처리 승인 필요" for cid in pending]
        return "조건부", None, None, preconditions

    return "가능", None, None, []


def _validate_inventory_resource(
    candidate: ResponseCandidate, inventory_state: dict
) -> tuple[str, str | None, str | None, list[str]] | None:
    text = f"{candidate.candidate_type} {candidate.description}"
    if not any(keyword in text for keyword in INVENTORY_KEYWORDS):
        return None

    shortages = [
        part_id
        for part_id, info in inventory_state.items()
        if info.get("safety_stock") is not None and info.get("qty", 0) <= info.get("safety_stock", 0)
    ]
    if shortages:
        detail = f"부품 {', '.join(shortages)} 재고가 이미 안전재고 이하로 소진되어 대체 투입 여력이 없음"
        return "불가능", "자원부족", detail, []

    return "조건부", None, None, ["생산관리팀의 대체 부품 적합성 확인 필요"]


def _cross_incident_conflicts(db: Session, incident_id: int, container_ids: list[str]) -> list[str]:
    if not container_ids:
        return []

    other_candidates = (
        db.query(ResponseCandidate)
        .join(Incident, ResponseCandidate.incident_id == Incident.id)
        .filter(Incident.status == ACTIVE_INCIDENT_STATUS)
        .filter(ResponseCandidate.incident_id != incident_id)
        .filter(ResponseCandidate.validation_status.in_(["가능", "조건부"]))
        .all()
    )

    conflicts: list[str] = []
    wanted = set(container_ids)
    for other in other_candidates:
        other_text = f"{other.description} " + " ".join(other.preconditions or [])
        other_ids = set(CONTAINER_ID_PATTERN.findall(other_text))
        overlap = other_ids & wanted
        if overlap:
            conflicts.append(
                f"사건 #{other.incident_id}의 후보 #{other.id}('{other.candidate_type}')와 "
                f"컨테이너 {', '.join(sorted(overlap))} 자원 중복"
            )
    return conflicts


def _validate_one(
    db: Session, incident_id: int, candidate: ResponseCandidate, snapshot_repo: OperationalSnapshotRepository
) -> dict:
    """Returns the field updates to apply to `candidate` (never mutates it
    directly -- the caller persists via the repository's update())."""

    snapshot = snapshot_repo.get(candidate.snapshot_id)
    operational_state = (snapshot.operational_state if snapshot else None) or {}
    transport_state = operational_state.get("transport") or {}
    inventory_state = operational_state.get("inventory") or {}
    known_container_ids = list(transport_state.keys())

    container_ids = _referenced_container_ids(candidate, known_container_ids)

    result = _validate_transport_resource(candidate, transport_state, container_ids)
    if result is None:
        result = _validate_inventory_resource(candidate, inventory_state)
    if result is None:
        result = ("가능", None, None, [])

    status, category, detail, precondition_additions = result

    if status != "불가능":
        conflicts = _cross_incident_conflicts(db, incident_id, container_ids)
        if conflicts:
            status = "불가능"
            category = "자원부족"
            detail = "다른 사건의 대응안과 자원(컨테이너)이 중복됨: " + "; ".join(conflicts)
            precondition_additions = []

    updates: dict = dict(validation_status=status, exclusion_category=category, exclusion_detail=detail)
    if status == "조건부" and precondition_additions:
        merged = list(dict.fromkeys((candidate.preconditions or []) + precondition_additions))
        updates["preconditions"] = merged
    return updates


def validate_candidates(db: Session, incident_id: int) -> list[ResponseCandidate]:
    """Stage 2 of the simulate pipeline. Reads every response_candidates row
    for this incident (regardless of current validation_status -- re-running
    this stage is idempotent/re-evaluates from scratch each time) and
    updates validation_status/exclusion_category/exclusion_detail/
    preconditions in place (response_candidates is mutable, see
    app/repositories/response_candidates.py).

    Raises IncidentNotFoundError if the incident does not exist. Returns an
    empty list (no error) if the incident exists but has no candidates yet
    -- that just means stage 1 has not run."""

    incident = IncidentRepository(db).get(incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"incident {incident_id} not found")

    candidate_repo = ResponseCandidateRepository(db)
    candidates = candidate_repo.for_incident(incident_id)
    if not candidates:
        return []

    snapshot_repo = OperationalSnapshotRepository(db)
    updated: list[ResponseCandidate] = []

    for candidate in candidates:
        if candidate.candidate_type == BASELINE_CANDIDATE_TYPE:
            # 무대응은 항상 실행 가능 -- 제약 검증을 거치지 않는 특수 케이스.
            updated.append(
                candidate_repo.update(
                    candidate.id,
                    validation_status="가능",
                    exclusion_category=None,
                    exclusion_detail=None,
                )
            )
            continue

        updates = _validate_one(db, incident_id, candidate, snapshot_repo)
        updated.append(candidate_repo.update(candidate.id, **updates))

    return updated
