"""Pydantic schemas for PATCH /sop/{sop_id}/status and
GET /incidents/{id}/timeline (agents/execution-tracking.md).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.services.execution_tracking import VALID_SOP_STATUSES


class SopStatusUpdate(BaseModel):
    """Request body for PATCH /sop/{sop_id}/status."""

    status: str = Field(..., description="수신 | 수락 | 시작 | 진행 | 완료 | 실패")
    actor: str = Field(..., min_length=1)
    note: str | None = None

    @field_validator("status")
    @classmethod
    def _known_status_only(cls, v: str) -> str:
        if v not in VALID_SOP_STATUSES:
            raise ValueError(f"status must be one of {VALID_SOP_STATUSES}")
        return v

    @field_validator("actor")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v


class SopStatusTransitionRead(BaseModel):
    """Response body for PATCH /sop/{sop_id}/status -- the newly appended
    audit_log row, plus the outcome of the deviation check that follows it
    (`deviation_check` is None when no deviation/re-evaluation was
    triggered by this transition)."""

    id: int
    incident_id: int | None
    sop_id: int
    status: str
    actor: str
    note: str | None
    created_at: datetime
    deviation_check: dict[str, Any] | None = None


class TimelineEvent(BaseModel):
    """One audit_log row, shaped for the frontend timeline view + deviation/
    escalation banner (ARCHITECTURE.md §7.1)."""

    id: int
    event_type: str
    actor: str
    reason: str | None
    sop_id: int | None
    status: str | None
    payload: dict[str, Any]
    created_at: datetime
    is_deviation_event: bool


class TimelineResponse(BaseModel):
    incident_id: int
    events: list[TimelineEvent]
