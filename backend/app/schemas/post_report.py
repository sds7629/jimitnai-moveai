"""Pydantic response schemas for GET /incidents/{id}/post-report,
GET /incidents/{id}/cost-attribution, GET /reports/roi (agents/post-report.md).

Same convention as app/schemas/decision_package.py: the 12-section post-report
body and the cost-attribution/ROI breakdowns are typed as `dict[str, Any]`
rather than expanded into dozens of nested Pydantic models -- their shape is
documented and enforced entirely in app/services/post_report.py,
app/services/cost_attribution.py and app/services/roi.py, the single places
that build them. What Pydantic *does* enforce here is that the top-level
fields themselves (report_status, sections, breakdown, scenarios, ...) are
always present and non-optional -- callers can rely on every key existing,
even when a given sub-section's content is an explicit
`{"available": False, "reason": ...}` placeholder.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class PostReportRead(BaseModel):
    """GET /incidents/{id}/post-report response -- always report_status='잠정'
    in this scope (see app/services/post_report.py module docstring)."""

    model_config = ConfigDict(extra="forbid")

    incident_id: int
    report_status: str
    actual_status: str
    scope_limitation_note: str
    generated_at: datetime
    sections: dict[str, Any]


class CostAttributionRead(BaseModel):
    """GET /incidents/{id}/cost-attribution response."""

    model_config = ConfigDict(extra="forbid")

    incident_id: int
    is_heuristic: bool
    rag_unavailable: bool
    heuristic_disclaimer: str
    avoided_loss_basis: dict[str, Any]
    matched_ld_clauses: list[dict[str, Any]]
    matched_dnd_clauses: list[dict[str, Any]]
    breakdown: dict[str, Any]
    classification_note: str


class RoiRead(BaseModel):
    """GET /reports/roi response -- incident-independent, global endpoint."""

    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, float]
    scenarios: dict[str, Any]
    disclosure: dict[str, Any]
