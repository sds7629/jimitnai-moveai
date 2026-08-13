"""POST /approvals/{id}/dispatch-sop, GET /incidents/{id}/sop-status
(agents/communication-sop.md).

Thin HTTP layer over app/services/communication.py -- all the guard logic
(승인/조건부승인 + incidents.status='승인' 확인, 멱등성) lives there; this
module only translates that service's exceptions into HTTP status codes,
same convention as every other API module in this codebase (app/api/
approvals.py, app/api/decision_package.py, ...).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.sop_dispatch import SopDispatchResultItem, SopStatusResponse
from app.services.communication import (
    ApprovalNotFoundError,
    IncidentNotFoundError,
    SopDispatchNotAllowedError,
    dispatch_sop,
    sop_status_for_incident,
)

router = APIRouter(tags=["communication-sop"])


@router.post("/approvals/{approval_id}/dispatch-sop", response_model=list[SopDispatchResultItem])
def dispatch_sop_endpoint(approval_id: int, db: Session = Depends(get_db)) -> list[SopDispatchResultItem]:
    try:
        results = dispatch_sop(db, approval_id)
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SopDispatchNotAllowedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return [SopDispatchResultItem.model_validate(r) for r in results]


@router.get("/incidents/{incident_id}/sop-status", response_model=SopStatusResponse)
def get_sop_status(incident_id: int, db: Session = Depends(get_db)) -> SopStatusResponse:
    try:
        statuses = sop_status_for_incident(db, incident_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return SopStatusResponse(incident_id=incident_id, sop_statuses=statuses)
