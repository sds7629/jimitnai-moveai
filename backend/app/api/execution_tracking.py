"""PATCH /sop/{sop_id}/status, GET /incidents/{id}/timeline
(agents/execution-tracking.md).

Thin HTTP layer over app/services/execution_tracking.py -- all the guard
logic (sop_id existence, status value validation, deviation detection and
delegation to orchestration) lives there; this module only translates that
service's exceptions into HTTP status codes, same convention as every other
API module in this codebase (app/api/approvals.py, app/api/sop_dispatch.py,
...).

`update_sop_status` is `async def` because the path where a deviation is
detected calls (via check_and_handle_deviation)
app.services.orchestration.handle_execution_deviation, which awaits
simulate_candidates's LLM calls -- CLAUDE.md 비동기 처리 원칙: any endpoint
whose *some* branch reaches a blocking LLM call must be async, even though
the common case (no deviation) never awaits anything itself.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm import LLMConfigError
from app.schemas.execution_tracking import (
    SopStatusTransitionRead,
    SopStatusUpdate,
    TimelineEvent,
    TimelineResponse,
)
from app.services.execution_tracking import (
    FAILED_STATUS,
    IncidentNotFoundError,
    InvalidSopStatusError,
    SopNotFoundError,
    check_and_handle_deviation,
    record_status_transition,
    timeline_for_incident,
)
from app.services.simulation import SimulationValidationError

router = APIRouter(tags=["execution-tracking"])


@router.patch("/sop/{sop_id}/status", response_model=SopStatusTransitionRead)
async def update_sop_status(
    sop_id: int, payload: SopStatusUpdate, db: Session = Depends(get_db)
) -> SopStatusTransitionRead:
    try:
        row = record_status_transition(db, sop_id, payload.status, payload.actor, payload.note)
    except SopNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidSopStatusError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # '실패'는 그 자체로 편차 신호(자원 취소/충돌에 준하는 실행 실패)로 취급해
    # detect_deviation의 시간 기반 조건과 무관하게 즉시 재평가를 위임한다 --
    # 그 외 상태는 detect_deviation이 판단(기한 내 미수락/지연된 완료)한다.
    additional_reason = None
    if payload.status == FAILED_STATUS:
        note_suffix = f" (note: {payload.note})" if payload.note else ""
        additional_reason = f"SOP {sop_id} 상태가 '{FAILED_STATUS}'로 기록됨{note_suffix}"

    try:
        deviation_result = await check_and_handle_deviation(
            db, row.incident_id, additional_reason=additional_reason
        )
    except SimulationValidationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return SopStatusTransitionRead(
        id=row.id,
        incident_id=row.incident_id,
        sop_id=sop_id,
        status=payload.status,
        actor=payload.actor,
        note=payload.note,
        created_at=row.created_at,
        deviation_check=deviation_result,
    )


@router.get("/incidents/{incident_id}/timeline", response_model=TimelineResponse)
def get_incident_timeline(incident_id: int, db: Session = Depends(get_db)) -> TimelineResponse:
    try:
        events = timeline_for_incident(db, incident_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return TimelineResponse(
        incident_id=incident_id,
        events=[TimelineEvent(**e) for e in events],
    )
