"""Pydantic response schemas for POST /approvals/{id}/dispatch-sop and
GET /incidents/{id}/sop-status (agents/communication-sop.md).

Both response shapes stay loosely typed (`dict[str, Any]` for the message
body / event payloads) for the same reason app/schemas/decision_package.py
does: the actual structure is documented and enforced in
app/services/communication.py, the single place that builds it, and
GET /incidents/{id}/sop-status is explicitly designed so a future wave
(execution-tracking) can add new event types without this schema changing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SopDispatchResultItem(BaseModel):
    """One role's SOP dispatch result. `sop_id` is the audit_log row id for
    that role's `sop_dispatched` event -- see app/services/communication.py
    module docstring for why there is no separate SOP table."""

    sop_id: int
    incident_id: int | None
    role: str | None
    approval_id: int | None
    dispatched_at: datetime
    action: str | None
    message_text: str | None


class SopStatusEvent(BaseModel):
    """One raw audit_log row referencing a given sop_id -- kept generic
    (event_type/payload passthrough) so this schema never needs to change
    when execution-tracking introduces new event types."""

    event_type: str
    actor: str
    reason: str | None
    payload: dict[str, Any]
    created_at: datetime


class SopStatusItem(BaseModel):
    """One SOP dispatch's status-tracker entry -- 발송·수신·수락·완료 상태.
    received_at/accepted_at/completed_at/failed_at stay null until
    execution-tracking appends the corresponding follow-up audit_log rows
    (payload={"sop_id": ..., "status": "수신"|"수락"|"완료"|"실패"})."""

    sop_id: int
    incident_id: int
    role: str | None
    approval_id: int | None
    action_summary: str | None
    dispatched_at: datetime
    dispatched_by: str
    status: str
    received_at: datetime | None
    accepted_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    events: list[SopStatusEvent]


class SopStatusResponse(BaseModel):
    incident_id: int
    sop_statuses: list[SopStatusItem]
