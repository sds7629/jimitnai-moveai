"""Pydantic response schema for GET /incidents/{id}/snapshots/latest
(agents/operational-graph.md).

Contract-first (ARCHITECTURE.md §7.3): the 운영 현황 대시보드 screen reads
this shape directly, and response-design/simulation (the next waves) read
the same `OperationalSnapshotRead.operational_state` / `.assumptions` /
`.data_version` / `.scenario_version` fields as their baseline input.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class OperationalSnapshotRead(BaseModel):
    """Full snapshot record, as persisted. `quality_mode`/`freshness_seconds`/
    `coverage_ratio` are the data-quality-gate fields the dashboard shows
    (agents/operational-graph.md work item #4)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    data_version: str
    scenario_version: str
    assumptions: list[str]
    operational_state: dict[str, Any]
    quality_mode: str
    freshness_seconds: int | None
    coverage_ratio: float | None
    created_at: datetime
