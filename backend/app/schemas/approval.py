"""Pydantic schemas for POST /incidents/{id}/approvals (agents/orchestration.md).

Contract-first per ARCHITECTURE.md §7.3 -- this is the request/response shape
the "승인/조건부승인/반려/수정요청 버튼 + 사유 입력 폼" screen (ARCHITECTURE.md
§7.1) is built against.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Mirrors app.services.orchestration.CLIENT_DECISION_TYPES -- '기한초과' is
# system-detected only (see app/services/orchestration.py's
# check_deadline_overrun) and must never be submittable through this
# request body, even before the service layer's own defense-in-depth check.
CLIENT_DECISION_TYPES: tuple[str, ...] = ("승인", "조건부승인", "수정요청", "반려")

# "조건부승인의 조건이 반드시 포함되도록 스키마에서 강제해라(빈 사유 금지 --
# 이미 DB 컬럼이 NOT NULL이지만 API 레벨에서 최소 길이 등으로 한 번 더 의미 있게
# 강제해라)" -- the business spec names no specific number, so this is a
# judgment call: 10 characters is enough to reject a rubber-stamp non-answer
# ("ok", "승인") while not being an unreasonable bar for a real Korean
# sentence describing an actual condition (e.g. "재고 확보 후 실행").
CONDITIONAL_APPROVAL_MIN_REASON_LENGTH = 10


class ApprovalCreate(BaseModel):
    """Request body for POST /incidents/{id}/approvals."""

    decision_type: str = Field(..., description="승인 | 조건부승인 | 수정요청 | 반려")
    reason: str = Field(..., min_length=1)
    approver: str = Field(..., min_length=1)

    @field_validator("decision_type")
    @classmethod
    def _client_decision_type_only(cls, v: str) -> str:
        if v not in CLIENT_DECISION_TYPES:
            raise ValueError(
                f"decision_type must be one of {CLIENT_DECISION_TYPES} -- "
                "'기한초과'는 시스템이 감지해 기록하는 값이라 클라이언트가 직접 지정할 수 없습니다"
            )
        return v

    @field_validator("reason", "approver")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v

    @model_validator(mode="after")
    def _conditional_approval_must_state_a_condition(self) -> "ApprovalCreate":
        if (
            self.decision_type == "조건부승인"
            and len(self.reason.strip()) < CONDITIONAL_APPROVAL_MIN_REASON_LENGTH
        ):
            raise ValueError(
                "조건부승인은 반영할 조건을 reason에 구체적으로 명시해야 합니다 "
                f"(최소 {CONDITIONAL_APPROVAL_MIN_REASON_LENGTH}자 이상, 현재 "
                f"{len(self.reason.strip())}자)"
            )
        return self


class ApprovalRead(BaseModel):
    """Full approvals row, as persisted (append-only -- see app/models/approval.py)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    decision_type: str
    reason: str
    approver: str
    decided_at: datetime
    data_version_ref: str | None
    scenario_version_ref: str | None
    created_at: datetime
