"""Pydantic response schemas for GET /incidents/{id}/impact-dag
(agents/operational-graph.md).

Each node carries its own affected_target/expected_time/basis/
responsible_party/uncertainty so the frontend's "노드 클릭 시 근거·불확실성
표시" interaction (ARCHITECTURE.md §7.1) has everything it needs without a
second request.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImpactDagNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    snapshot_id: int
    node_key: str
    label: str
    affected_target: str | None
    expected_time: datetime | None
    basis: str | None
    responsible_party: str | None
    uncertainty: str | None
    created_at: datetime


class ImpactDagEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    snapshot_id: int
    from_node_id: int
    to_node_id: int
    basis: str | None
    created_at: datetime


class ImpactDagRead(BaseModel):
    """GET /incidents/{id}/impact-dag response — the snapshot identity
    fields are echoed alongside nodes/edges so the frontend can show which
    data/scenario version the currently-rendered graph belongs to."""

    incident_id: int
    snapshot_id: int
    data_version: str
    scenario_version: str
    quality_mode: str
    nodes: list[ImpactDagNodeRead]
    edges: list[ImpactDagEdgeRead]
