"""Pydantic response schemas for the simulate pipeline API
(agents/response-design.md, agents/constraint-validation.md,
agents/simulation.md), i.e. `POST /incidents/{id}/simulate` and
`GET /incidents/{id}/candidates`.

`CandidateWithLatestSimulation` is the one shape the frontend's "대응안 비교
카드" (ARCHITECTURE.md §7.1) needs -- a candidate plus its validation state
plus (if one has ever been computed) its most recent simulation result, all
in a single response so the card can render without a second round trip per
candidate.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SimulationResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    incident_id: int
    expected_loss: float | None
    p90: float | None
    cvar: float | None
    sensitivity_variables: list[Any]
    confidence: float | None
    fact: dict[str, Any]
    inference: dict[str, Any]
    assumption: dict[str, Any]
    data_version: str
    scenario_version: str
    created_at: datetime


class CandidateWithLatestSimulation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    snapshot_id: int
    candidate_type: str
    description: str
    reference_document_ids: list[Any]
    preconditions: list[Any]
    start_time_variant: str | None
    validation_status: str
    exclusion_category: str | None
    exclusion_detail: str | None
    created_at: datetime
    updated_at: datetime
    latest_simulation: SimulationResultRead | None = None


class CandidatesListResponse(BaseModel):
    incident_id: int
    candidates: list[CandidateWithLatestSimulation]


class SimulatePipelineResponse(BaseModel):
    """POST /incidents/{id}/simulate response. `reused_existing_candidates`
    documents which re-run policy branch was taken (see
    app/api/simulate.py module docstring for the reasoning)."""

    incident_id: int
    reused_existing_candidates: bool
    candidate_count: int
    validated_count: int
    simulated_count: int
