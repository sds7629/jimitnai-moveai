"""GET /incidents/{id}/impact-dag (agents/operational-graph.md).

Same lazy-create as app/api/snapshots.py — the DAG is always built together
with its owning snapshot in ensure_snapshot_and_dag, so this endpoint just
resolves the snapshot (creating it if missing) and reads its nodes/edges.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories.impact_dag import ImpactDagEdgeRepository, ImpactDagNodeRepository
from app.schemas.impact_dag import ImpactDagRead
from app.services.operational_graph import (
    IncidentNotEligibleError,
    IncidentNotFoundError,
    ensure_snapshot_and_dag,
)

router = APIRouter(prefix="/incidents", tags=["operational-graph"])


@router.get("/{incident_id}/impact-dag", response_model=ImpactDagRead)
def get_impact_dag(incident_id: int, db: Session = Depends(get_db)) -> ImpactDagRead:
    try:
        snapshot = ensure_snapshot_and_dag(db, incident_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IncidentNotEligibleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    nodes = ImpactDagNodeRepository(db).for_snapshot(snapshot.id)
    edges = ImpactDagEdgeRepository(db).for_snapshot(snapshot.id)

    return ImpactDagRead(
        incident_id=incident_id,
        snapshot_id=snapshot.id,
        data_version=snapshot.data_version,
        scenario_version=snapshot.scenario_version,
        quality_mode=snapshot.quality_mode,
        nodes=nodes,
        edges=edges,
    )
