"""Pydantic schemas for the incident-intake API (POST/GET /incidents).

Contract-first per ARCHITECTURE.md §7.3: this module is the shared contract
between the (not-yet-built) frontend and this backend module, and the only
piece the operational-graph wave needs to read to know what
`incidents.assumptions` looks like.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Mirrors the CHECK constraint on incidents.status (db/init/002-schema.sql
# line 32). Kept here as the single app-layer source of truth for status
# validation since there is no shared enum between SQL DDL and the ORM in
# this codebase.
INCIDENT_STATUSES: tuple[str, ...] = ("신규", "중복", "오탐", "유효", "처리중", "승인", "종료")

# The four affected-target categories the business spec calls out explicitly
# (simulation-supply-chain-tool.md §3.1: "영향 가능 화물·부품·생산오더·고객").
# These are optional at input time — a first report may not know all of them
# yet — but their absence must surface as an explicit assumption, never be
# silently dropped (agents/incident-intake.md).
AFFECTED_TARGET_KEYS: tuple[str, ...] = ("containers", "parts", "production_orders", "customers")


class AffectedTargets(BaseModel):
    """Shape matches the seed scenarios (db/init/003-seed-scenarios.sql):
    containers/parts/production_orders/customers, each a list of free-text
    identifiers. `extra="allow"` keeps this open to genuinely free input
    (e.g. a category the seed data doesn't use) without rejecting the
    request — this endpoint must accept both the 3 fixed seed scenarios and
    arbitrary free-form incident reports.
    """

    model_config = ConfigDict(extra="allow")

    containers: list[str] | None = None
    parts: list[str] | None = None
    production_orders: list[str] | None = None
    customers: list[str] | None = None


class IncidentCreate(BaseModel):
    """Request schema for POST /incidents.

    Only type/location/occurred_at are hard-required (§3.1: "사건 유형,
    발생 위치와 최초 발생시각"). affected_targets is optional — its absence,
    in whole or in part, is handled as an explicit ASSUMPTION by the service
    layer rather than rejected or silently defaulted.
    """

    type: str = Field(..., min_length=1, description="사건 유형, 예: '항만 적체', '파업', '관세'")
    location: str = Field(..., min_length=1, description="발생 위치, 예: '부산항 3부두'")
    occurred_at: datetime = Field(..., description="최초 발생시각")
    affected_targets: AffectedTargets | None = Field(
        default=None,
        description="영향 가능 화물/부품/생산오더/고객. 미제공 시 가정으로 명시됨.",
    )

    @field_validator("type", "location")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v


class IncidentRead(BaseModel):
    """Full incident record, as persisted."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    location: str
    occurred_at: datetime
    status: str
    duplicate_of_incident_id: int | None
    affected_targets: dict[str, Any]
    assumptions: list[str]
    created_at: datetime
    updated_at: datetime


class IncidentCreateResponse(IncidentRead):
    """POST /incidents response.

    Adds the missing-field list computed at intake time
    (agents/incident-intake.md work item #4). The same information is also
    persisted verbatim as human-readable strings into `incidents.assumptions`
    (see app/services/incident_intake.py) — that column is what the
    operational-graph wave reads when it builds the operational snapshot's
    own `assumptions` list. `missing_fields` here is a convenience echo for
    the caller of this one request; it is not separately persisted.
    """

    missing_fields: list[str] = Field(default_factory=list)
    duplicate_detected: bool = False


class IncidentListItem(BaseModel):
    """Lighter shape for GET /incidents — the 사건 목록·상태 뱃지 screen
    (ARCHITECTURE.md §7.1) only needs identity + status, not the full
    affected_targets/assumptions payload."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    location: str
    occurred_at: datetime
    status: str
    duplicate_of_incident_id: int | None
    created_at: datetime


class IncidentDismissRequest(BaseModel):
    """Body for marking an incident 오탐 (false positive) or 종료 (closed).

    `reason` is mandatory — agents/incident-intake.md is explicit that
    "사유 없는 자동 종료는 금지" (no automatic closure without a reason).
    There is deliberately no default/empty-string fallback.
    """

    reason: str = Field(..., min_length=1)
    actor: str = Field(default="operator", min_length=1)

    @field_validator("reason", "actor")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v
