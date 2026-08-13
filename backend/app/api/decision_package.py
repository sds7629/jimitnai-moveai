"""GET /incidents/{id}/decision-package (agents/response-optimization.md).

Re-run / re-cache policy (a judgment call this wave had to make, mirroring
app/api/simulate.py's "재실행 정책" precedent -- there is no orchestration
wave yet to emit an explicit "동적 변수가 유의미하게 바뀌었다" recompute signal,
per simulation-supply-chain-tool.md §7.2/§3.3):

  - `decision_packages` is append-only (no update() on the repository), so
    "recompute" always means inserting a brand-new row, never patching the
    latest one.
  - This endpoint compares the latest existing package's created_at
    against both (a) the most recent simulation_results row's created_at
    and (b) the most recent candidate_reviews row's created_at for the
    incident (across all its candidates): if a simulation has completed, or
    a 다중 관점 교차검증 review has been (re-)appended, *after* the current
    latest package was built -- or no package exists yet at all -- a fresh
    package is built and returned. Otherwise the existing latest package is
    reused as-is.
  - This guarantees the one hard requirement from the wave brief ("시뮬레이
    션이 새로 갱신됐는데 패키지가 그 이전 걸 캐싱해서 보여주는 일은 없어야 한다"),
    now extended to reviews (a fresh /simulate call's stage 4 appends new
    candidate_reviews rows too -- those must not be served stale either),
    while not silently piling up an identical new row on every unrelated
    GET call for an incident whose simulation results and reviews have not
    changed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories.candidate_reviews import CandidateReviewRepository
from app.repositories.decision_packages import DecisionPackageRepository
from app.repositories.simulation_results import SimulationResultRepository
from app.schemas.decision_package import DecisionPackageRead
from app.services.orchestration import check_deadline_overrun
from app.services.response_optimization import (
    IncidentNotEligibleError,
    IncidentNotFoundError,
    build_decision_package,
)

router = APIRouter(prefix="/incidents", tags=["response-optimization"])


@router.get("/{incident_id}/decision-package", response_model=DecisionPackageRead)
def get_decision_package(incident_id: int, db: Session = Depends(get_db)) -> DecisionPackageRead:
    package_repo = DecisionPackageRepository(db)
    sim_repo = SimulationResultRepository(db)
    review_repo = CandidateReviewRepository(db)

    existing = package_repo.latest_for_incident(incident_id)
    # for_incident() orders by created_at ascending -- the last element (if
    # any) is the most recently produced simulation_results/candidate_reviews
    # row for this incident, across every one of its candidates.
    sims = sim_repo.for_incident(incident_id)
    latest_sim_created_at = sims[-1].created_at if sims else None
    reviews = review_repo.for_incident(incident_id)
    latest_review_created_at = reviews[-1].created_at if reviews else None

    needs_recompute = (
        existing is None
        or (latest_sim_created_at is not None and latest_sim_created_at > existing.created_at)
        or (latest_review_created_at is not None and latest_review_created_at > existing.created_at)
    )

    if needs_recompute:
        try:
            package = build_decision_package(db, incident_id)
        except IncidentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except IncidentNotEligibleError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    else:
        package = existing

    # 결정기한 초과 감지 (agents/orchestration.md work item #5): "요청이 들어올
    # 때" 체크하는 두 지점 중 하나가 바로 이 GET 호출이다 -- 실제 알림 발송은
    # 하지 않고, 아직 기록되지 않았다면 approvals(+audit_log)에 '기한초과'를
    # 기록만 한다(app/services/orchestration.py 참고). 이 응답의 모양(package
    # 자체)에는 영향을 주지 않는 순수 side-effect 체크라 반환값은 쓰지 않는다.
    check_deadline_overrun(db, incident_id)

    return DecisionPackageRead.model_validate(package)
