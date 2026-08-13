"""POST /incidents/{id}/simulate + GET /incidents/{id}/candidates
(agents/response-design.md, agents/constraint-validation.md,
agents/simulation.md, agents/response-optimization.md).

This is the one pipeline all four "simulate" personas share: candidate
generation (stage 1) -> constraint validation (stage 2) -> LLM-based loss
simulation (stage 3) -> 다중 관점 교차검증 (stage 4, cost/feasibility/risk
cross-review), run in that fixed order
(simulation-supply-chain-tool.md §7.3) against the shared
response_candidates / simulation_results / candidate_reviews tables.

Re-run policy (a judgment call this wave had to make -- there is no
separate "reset candidates" endpoint and response_candidates is mutable,
not append-only, so both directions were possible):
  - If the incident has *no* response_candidates rows yet, stage 1
    (generate_candidates) runs and creates them (baseline + LLM candidates).
  - If it already has candidates -- either because this incident is one of
    the 3 seeded scenarios (db/init/003-seed-scenarios.sql seeds baseline +
    1 active candidate directly) or because /simulate already ran once for
    it -- stage 1 is *skipped* and the existing candidate rows are reused
    as-is. Rationale: response_candidates rows are themselves a decision the
    system already made (candidate_type/description/preconditions); a
    caller re-triggering /simulate (e.g. after a snapshot recompute, per
    simulation-supply-chain-tool.md §6.3 "재계산") almost always wants a
    fresh constraint check + fresh simulation against the *same* candidate
    set, not an ever-growing pile of duplicate candidates each time. If a
    genuinely new set of candidates is ever needed, that is a job for a
    dedicated "regenerate candidates" action in a future wave, not the
    default behavior of re-POSTing here.
  - Stages 2, 3 and 4 always re-run on every call regardless of the branch
    above: stage 2 (validate_candidates) just re-evaluates and updates the
    same mutable rows in place, stage 3 (simulate_candidates) always
    appends new simulation_results rows (append-only -- see
    app/repositories/simulation_results.py), which is exactly the
    "재시뮬레이션 트리거" behavior agents/simulation.md work item #5
    requires, and stage 4 (review_candidates_for_incident) always appends a
    fresh set of candidate_reviews rows (also append-only) against
    whichever simulation_results rows stage 3 just produced -- a re-run
    re-reviews against the newest numbers rather than reusing stale
    cross-review verdicts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm import LLMConfigError
from app.repositories.incidents import IncidentRepository
from app.repositories.response_candidates import ResponseCandidateRepository
from app.repositories.simulation_results import SimulationResultRepository
from app.schemas.simulate import (
    CandidatesListResponse,
    CandidateWithLatestSimulation,
    SimulatePipelineResponse,
    SimulationResultRead,
)
from app.services.candidate_review import CandidateReviewError, review_candidates_for_incident
from app.services.constraint_validation import validate_candidates
from app.services.operational_graph import (
    IncidentNotEligibleError,
    IncidentNotFoundError,
    ensure_snapshot_and_dag,
)
from app.services.response_design import ResponseGenerationError, generate_candidates
from app.services.simulation import SimulationValidationError, simulate_candidates

router = APIRouter(prefix="/incidents", tags=["simulate"])


@router.post("/{incident_id}/simulate", response_model=SimulatePipelineResponse)
async def trigger_simulate_pipeline(incident_id: int, db: Session = Depends(get_db)) -> SimulatePipelineResponse:
    candidate_repo = ResponseCandidateRepository(db)

    try:
        existing_candidates = candidate_repo.for_incident(incident_id)
        reused_existing = bool(existing_candidates)
        if not reused_existing:
            await generate_candidates(db, incident_id)
        else:
            # Still must validate the incident exists and is status='유효'
            # even on the reuse branch -- ensure_snapshot_and_dag performs
            # exactly that check and is a no-op write-wise when a snapshot
            # already exists (lazy-create contract).
            ensure_snapshot_and_dag(db, incident_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IncidentNotEligibleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ResponseGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    validated = validate_candidates(db, incident_id)

    try:
        simulated = await simulate_candidates(db, incident_id)
    except SimulationValidationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        reviewed = await review_candidates_for_incident(db, incident_id)
    except CandidateReviewError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    candidate_count = len(candidate_repo.for_incident(incident_id))

    return SimulatePipelineResponse(
        incident_id=incident_id,
        reused_existing_candidates=reused_existing,
        candidate_count=candidate_count,
        validated_count=len(validated),
        simulated_count=len(simulated),
        reviewed_count=len(reviewed),
    )


@router.get("/{incident_id}/candidates", response_model=CandidatesListResponse)
def get_candidates(incident_id: int, db: Session = Depends(get_db)) -> CandidatesListResponse:
    incident = IncidentRepository(db).get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"incident {incident_id} not found")

    candidate_repo = ResponseCandidateRepository(db)
    sim_repo = SimulationResultRepository(db)

    items = []
    for candidate in candidate_repo.for_incident(incident_id):
        latest_sim = sim_repo.latest_for_candidate(candidate.id)
        items.append(
            CandidateWithLatestSimulation(
                id=candidate.id,
                incident_id=candidate.incident_id,
                snapshot_id=candidate.snapshot_id,
                candidate_type=candidate.candidate_type,
                description=candidate.description,
                reference_document_ids=candidate.reference_document_ids,
                preconditions=candidate.preconditions,
                start_time_variant=candidate.start_time_variant,
                validation_status=candidate.validation_status,
                exclusion_category=candidate.exclusion_category,
                exclusion_detail=candidate.exclusion_detail,
                created_at=candidate.created_at,
                updated_at=candidate.updated_at,
                latest_simulation=SimulationResultRead.model_validate(latest_sim) if latest_sim else None,
            )
        )

    return CandidatesListResponse(incident_id=incident_id, candidates=items)
