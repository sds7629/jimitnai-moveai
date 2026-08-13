"""POST /incidents/{id}/approvals (agents/orchestration.md).

Thin HTTP layer over app/services/orchestration.py's explicit 4-branch state
machine (승인/조건부승인/수정요청/반려 -- '기한초과' is system-detected only, see
check_deadline_overrun, and is rejected by app/schemas/approval.py before it
ever reaches here).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm import LLMConfigError
from app.repositories.incidents import IncidentRepository
from app.schemas.approval import ApprovalCreate, ApprovalRead
from app.services.orchestration import (
    IncidentNotFoundError,
    UnknownDecisionTypeError,
    process_approval,
)
from app.services.simulation import SimulationValidationError

router = APIRouter(prefix="/incidents", tags=["orchestration"])


@router.post("/{incident_id}/approvals", response_model=ApprovalRead, status_code=201)
async def create_approval(
    incident_id: int, payload: ApprovalCreate, db: Session = Depends(get_db)
) -> ApprovalRead:
    # Checked up front for a clean 404 message before process_approval's own
    # (identical) check -- keeps the "incident not found" path readable at
    # this layer without relying on exception-message parsing.
    if IncidentRepository(db).get(incident_id) is None:
        raise HTTPException(status_code=404, detail=f"incident {incident_id} not found")

    try:
        approval = await process_approval(
            db,
            incident_id,
            decision_type=payload.decision_type,
            reason=payload.reason,
            approver=payload.approver,
        )
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnknownDecisionTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SimulationValidationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ApprovalRead.model_validate(approval)
