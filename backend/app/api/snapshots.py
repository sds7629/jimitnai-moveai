"""GET /incidents/{id}/snapshots/latest (agents/operational-graph.md).

Lazy-create per work item: there is no separate POST endpoint anywhere in
this system for building a snapshot. This GET is the only trigger — if none
exists yet, ensure_snapshot_and_dag builds one on the way through.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.snapshot import OperationalSnapshotRead
from app.services.operational_graph import (
    IncidentNotEligibleError,
    IncidentNotFoundError,
    ensure_snapshot_and_dag,
)

router = APIRouter(prefix="/incidents", tags=["operational-graph"])


@router.get("/{incident_id}/snapshots/latest", response_model=OperationalSnapshotRead)
def get_latest_snapshot(incident_id: int, db: Session = Depends(get_db)) -> OperationalSnapshotRead:
    try:
        snapshot = ensure_snapshot_and_dag(db, incident_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IncidentNotEligibleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return snapshot
