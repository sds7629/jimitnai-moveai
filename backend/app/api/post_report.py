"""GET /incidents/{id}/post-report, GET /incidents/{id}/cost-attribution,
GET /reports/roi (agents/post-report.md).

Thin HTTP layer over app/services/post_report.py, app/services/
cost_attribution.py and app/services/roi.py -- all three service functions
are pure synchronous aggregation over already-persisted data (no LLM call
anywhere in this wave), so every endpoint here is a plain `def`, same as
every other read-only GET in this codebase whose service layer has no
blocking I/O of its own beyond local Postgres reads.

`GET /incidents/{id}/post-report` recomputes on every call rather than
reading from a dedicated storage table -- see app/services/post_report.py's
module docstring for why no new table was introduced this wave.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.post_report import CostAttributionRead, PostReportRead, RoiRead
from app.services.cost_attribution import IncidentNotFoundError, classify_cost_attribution
from app.services.post_report import build_post_report
from app.services.roi import DEFAULT_ROI_INPUTS, compute_roi

router = APIRouter(tags=["post-report"])


@router.get("/incidents/{incident_id}/post-report", response_model=PostReportRead)
def get_post_report(incident_id: int, db: Session = Depends(get_db)) -> PostReportRead:
    try:
        report = build_post_report(db, incident_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PostReportRead.model_validate(report)


@router.get("/incidents/{incident_id}/cost-attribution", response_model=CostAttributionRead)
def get_cost_attribution(incident_id: int, db: Session = Depends(get_db)) -> CostAttributionRead:
    try:
        result = classify_cost_attribution(db, incident_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CostAttributionRead.model_validate(result)


@router.get("/reports/roi", response_model=RoiRead)
def get_roi(
    annual_incident_frequency: float = Query(
        default=DEFAULT_ROI_INPUTS["annual_incident_frequency"],
        gt=0,
        description="사고 유형별 연간 발생 빈도 (건/년)",
    ),
    expected_loss_per_incident: float = Query(
        default=DEFAULT_ROI_INPUTS["expected_loss_per_incident"],
        gt=0,
        description="사고당 기대손실 (원)",
    ),
    intervention_ratio: float = Query(
        default=DEFAULT_ROI_INPUTS["intervention_ratio"],
        ge=0,
        le=1,
        description="시스템이 개입 가능한 비율 (0~1)",
    ),
    execution_rate: float = Query(
        default=DEFAULT_ROI_INPUTS["execution_rate"],
        ge=0,
        le=1,
        description="대응 실행률 (0~1)",
    ),
    loss_reduction_rate: float = Query(
        default=DEFAULT_ROI_INPUTS["loss_reduction_rate"],
        ge=0,
        le=1,
        description="실제 손실 감소율 (0~1)",
    ),
    total_investment: float = Query(
        default=DEFAULT_ROI_INPUTS["total_investment"],
        gt=0,
        description="총 구축·운영비 (원)",
    ),
) -> RoiRead:
    result = compute_roi(
        annual_incident_frequency=annual_incident_frequency,
        expected_loss_per_incident=expected_loss_per_incident,
        intervention_ratio=intervention_ratio,
        execution_rate=execution_rate,
        loss_reduction_rate=loss_reduction_rate,
        total_investment=total_investment,
    )
    return RoiRead.model_validate(result)
