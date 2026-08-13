"""POST/GET /incidents — the entry point of the whole workflow
(agents/incident-intake.md). See app/services/incident_intake.py for the
actual validation/classification logic; this module is just the HTTP layer.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories.incidents import IncidentRepository
from app.schemas.incident import (
    INCIDENT_STATUSES,
    IncidentCreate,
    IncidentCreateResponse,
    IncidentDismissRequest,
    IncidentListItem,
    IncidentRead,
)
from app.services.incident_intake import create_incident, dismiss_incident

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.post("", response_model=IncidentCreateResponse, status_code=201)
def report_incident(payload: IncidentCreate, db: Session = Depends(get_db)) -> IncidentCreateResponse:
    """Accepts a new incident report (seed scenario or free-form), runs
    duplicate/missing-field checks, persists the classified row, and
    returns it along with the missing_fields it detected."""

    result = create_incident(db, payload)
    return IncidentCreateResponse(
        **IncidentRead.model_validate(result.incident).model_dump(),
        missing_fields=result.missing_fields,
        duplicate_detected=result.duplicate_detected,
    )


@router.get("", response_model=list[IncidentListItem])
def list_incidents(
    status: str | None = Query(
        default=None, description="상태 뱃지 필터: 신규/중복/오탐/유효/처리중/승인/종료"
    ),
    db: Session = Depends(get_db),
) -> list[IncidentListItem]:
    if status is not None and status not in INCIDENT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"invalid status filter: {status!r}, must be one of {INCIDENT_STATUSES}",
        )
    repo = IncidentRepository(db)
    return repo.list_by_status(status)


@router.post("/{incident_id}/dismiss", response_model=IncidentRead)
def dismiss(
    incident_id: int, payload: IncidentDismissRequest, db: Session = Depends(get_db)
) -> IncidentRead:
    """Marks an incident 오탐 (false positive). `reason` is mandatory at the
    schema layer (IncidentDismissRequest) — no automatic/silent closure is
    possible through this endpoint."""

    updated = dismiss_incident(
        db, incident_id, reason=payload.reason, actor=payload.actor, new_status="오탐"
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"incident {incident_id} not found")
    return updated
