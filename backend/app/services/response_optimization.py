"""대응 최적화 에이전트 (agents/response-optimization.md).

Pure aggregation/calculation over what earlier stages already produced --
**no LLM call anywhere in this module** (per the wave brief and
CLAUDE.md's 비동기 처리 원칙: async is reserved for actual blocking I/O, and
there is none here), so every function here is a plain synchronous `def`
over local Postgres reads via the existing repository layer.

`build_decision_package` assembles the `decision_packages.package` JSONB
blob so that it always carries all 10 items required by
simulation-supply-chain-tool.md §5.1 -- never optional/sometimes-missing
sub-keys, even in the extreme case where every non-baseline candidate has
been excluded (see `_EMPTY_...` builders below, which still produce an
empty-but-present structure rather than omitting the key):

  1. expected_loss_p90_cvar   -- straight from each candidate's latest
                                  simulation_results row
  2. now_vs_6h_vs_no_action    -- baseline vs a start_time_variant='now'/
                                  '즉시' candidate vs a '+6h' candidate
  3. causal_path               -- latest snapshot's Impact DAG node/edge
                                  summary (label order + each node's basis)
  4. data_and_documents_used   -- snapshot.assumptions + each candidate's
                                  reference_document_ids
  5. fact_inference_assumption -- each candidate's latest sim result's
                                  fact/inference/assumption JSONB, verbatim
  6. freshness_and_coverage    -- snapshot.quality_mode/freshness_seconds/
                                  coverage_ratio
  7. key_sensitivity_variables -- each candidate's sensitivity_variables
  8. feasibility_and_exclusion -- every candidate's validation_status/
                                  exclusion_category/exclusion_detail/
                                  preconditions (including candidates that
                                  were never simulated at all)
  9. confidence_and_uncertainty -- each candidate's confidence + a P90/
                                  CVaR-derived uncertainty spread
  10. recommended_deadline     -- see `compute_recommended_deadline` below

Plus `ranked_candidates`, which is the actual "대응 조합 순위화" deliverable
(agents/response-optimization.md work item #2) -- kept as its own top-level
key alongside (not instead of) the 10 required items above.

Plus `cross_perspective_reviews` -- the 다중 관점 교차검증 (multi-perspective
cross-review, simulation-supply-chain-tool.md §7.1 "Level 2") results from
app/services/candidate_review.py exposed verbatim per candidate/lens, so a
human reviewer can see *why* a candidate ranked where it did, not just the
final composite_score. This is additional transparency alongside the 10
required items, not a replacement for any of them.

No text in this module ever asserts that a given candidate/ranking "is the
answer" -- see `DISCLAIMER` below, which is carried into every package. The
lens reviews surfaced in `cross_perspective_reviews` are concerns raised by
independent LLM calls, never a verdict -- see that section's own `note`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.candidate_review import CandidateReview
from app.models.impact_dag import ImpactDagEdge, ImpactDagNode
from app.models.operational_snapshot import OperationalSnapshot
from app.models.response_candidate import ResponseCandidate
from app.models.simulation_result import SimulationResult
from app.models.decision_package import DecisionPackage
from app.repositories.candidate_reviews import CandidateReviewRepository
from app.repositories.decision_packages import DecisionPackageRepository
from app.repositories.impact_dag import ImpactDagEdgeRepository, ImpactDagNodeRepository
from app.repositories.response_candidates import ResponseCandidateRepository
from app.repositories.simulation_results import SimulationResultRepository
from app.services.operational_graph import (
    IncidentNotEligibleError,  # re-exported for API layer convenience
    IncidentNotFoundError,  # re-exported for API layer convenience
    ensure_snapshot_and_dag,
)

__all__ = [
    "build_decision_package",
    "rank_candidates",
    "compute_recommended_deadline",
    "IncidentNotFoundError",
    "IncidentNotEligibleError",
    "IRREVERSIBLE_NODE_KEYS",
]

BASELINE_CANDIDATE_TYPE = "baseline"
NOW_START_TIME_VARIANTS = ("now", "즉시")
PLUS_6H_START_TIME_VARIANT = "+6h"

# "돌이킬 수 없는 지점" candidates, checked in priority order -- the node
# where real damage actually starts (production_halt for 적체/파업,
# production_impact for 관세/기타 -- see
# app/services/operational_graph.py's SCENARIO_TEMPLATES). inventory_depletion
# is the documented fallback (agents/response-optimization.md work item #3)
# for a DAG that, for whatever reason, has no production node at all.
IRREVERSIBLE_NODE_KEYS: tuple[str, ...] = ("production_halt", "production_impact")
FALLBACK_IRREVERSIBLE_NODE_KEY = "inventory_depletion"

DISCLAIMER = (
    "이 패키지는 대응안의 순위와 근거를 제공할 뿐, 특정 대응안을 정답으로 단정하지 않습니다. "
    "최종 의사결정은 담당자가 수행합니다."
)


# ------------------------------------------------------------------
# JSON-safety helpers -- JSONB persistence needs plain JSON types; the
# repository layer stores this dict as-is, so datetimes/Decimals must be
# converted before they ever reach DecisionPackageRepository.add().
# ------------------------------------------------------------------


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _to_float(value: Decimal | float | None) -> float | None:
    return float(value) if value is not None else None


# ------------------------------------------------------------------
# Decision deadline -- reverse-calculated from the Impact DAG's own
# structure, never a hardcoded offset (agents/response-optimization.md
# work item #3 / DoD case 3).
# ------------------------------------------------------------------


def compute_recommended_deadline(
    nodes: list[ImpactDagNode], edges: list[ImpactDagEdge]
) -> tuple[datetime | None, dict[str, Any]]:
    """Reverse-calculates a recommended decision deadline purely from a
    snapshot's own Impact DAG nodes/edges -- no fixed hour offset anywhere.

    Step 1: find the "돌이킬 수 없는 지점" (irreversible point) node --
    production_halt/production_impact if either is present in this DAG,
    else inventory_depletion (§5.1 fallback wording).

    Step 2: the deadline is *not* that node's own expected_time (reporting
    the disaster is not the same as giving a decision deadline before it).
    It is the expected_time of the node immediately preceding the
    irreversible node in the DAG, found via the edge whose to_node_id is
    the irreversible node's id. Per every scenario template in
    app/services/operational_graph.py, that preceding node's own edge
    basis text states, in scenario-specific business terms, that reaching
    it makes the irreversible node's outcome essentially locked in (e.g.
    "안전재고 소진 시점 도달 시 라인 가동 불가") -- so "decide by the time that
    predecessor event lands" is a DAG-derived deadline, not an arbitrary
    constant. Both expected_time values are themselves computed per
    incident from that incident's own inventory/consumption numbers, so
    the resulting deadline moves with the data, not with a constant in
    this module.

    Returns (None, {"note": ...}) when there is not enough DAG structure
    to compute anything (e.g. no nodes at all -- callers must not treat
    this as an error, just an absent deadline)."""

    if not nodes:
        return None, {"note": "Impact DAG 노드가 없어 결정기한을 계산할 수 없음"}

    # First node with a given node_key wins -- node_repo.for_snapshot()
    # orders by id ascending (insertion order), so this is the earliest
    # instance of each key within this one snapshot's DAG.
    nodes_by_key: dict[str, ImpactDagNode] = {}
    for n in nodes:
        nodes_by_key.setdefault(n.node_key, n)

    irreversible_node: ImpactDagNode | None = None
    irreversible_key: str | None = None
    for key in IRREVERSIBLE_NODE_KEYS:
        if key in nodes_by_key:
            irreversible_node = nodes_by_key[key]
            irreversible_key = key
            break
    if irreversible_node is None and FALLBACK_IRREVERSIBLE_NODE_KEY in nodes_by_key:
        irreversible_node = nodes_by_key[FALLBACK_IRREVERSIBLE_NODE_KEY]
        irreversible_key = FALLBACK_IRREVERSIBLE_NODE_KEY

    if irreversible_node is None or irreversible_node.expected_time is None:
        return None, {
            "note": (
                "돌이킬 수 없는 지점(production_halt/production_impact/inventory_depletion) "
                "노드를 찾지 못했거나 예상시각이 없어 결정기한을 계산할 수 없음"
            )
        }

    nodes_by_id = {n.id: n for n in nodes}
    predecessor: ImpactDagNode | None = None
    for e in edges:
        if e.to_node_id == irreversible_node.id:
            predecessor = nodes_by_id.get(e.from_node_id)
            break

    if predecessor is not None and predecessor.expected_time is not None:
        deadline = predecessor.expected_time
        basis_node_key = predecessor.node_key
        basis_node_label = predecessor.label
        basis = (
            f"'{predecessor.label}'({predecessor.node_key}) 예상시각을 결정기한으로 역산함 -- "
            f"이 시점 이후에는 '{irreversible_node.label}'({irreversible_key})이 사실상 되돌릴 수 없음"
        )
    else:
        # No predecessor edge found (malformed/partial DAG) -- still return
        # a deadline (the irreversible node's own expected_time) rather
        # than None, but flag that no lead time could be derived.
        deadline = irreversible_node.expected_time
        basis_node_key = irreversible_key
        basis_node_label = irreversible_node.label
        basis = (
            f"선행 노드를 찾지 못해 '{irreversible_node.label}'({irreversible_key}) 자체의 예상시각을 "
            "결정기한으로 사용함 (역산 불가)"
        )

    detail = {
        "irreversible_node_key": irreversible_key,
        "irreversible_node_label": irreversible_node.label,
        "irreversible_expected_time": irreversible_node.expected_time,
        "deadline_basis_node_key": basis_node_key,
        "deadline_basis_node_label": basis_node_label,
        "deadline_basis_expected_time": deadline,
        "basis": basis,
        "impact_if_exceeded": (
            f"{irreversible_node.label} (영향대상: {irreversible_node.affected_target}) 발생 예상 -- "
            f"근거: {irreversible_node.basis}"
        ),
    }
    return deadline, detail


# ------------------------------------------------------------------
# Ranking -- combines expected_loss/P90/CVaR with a feasibility penalty
# from validation_status + precondition count. Deliberately not a
# single-field sort (agents/response-optimization.md work item #2 /
# persona doc: "하드코딩된 단일 기준 정렬 금지" in spirit).
# ------------------------------------------------------------------


def _risk_score(sim: SimulationResult) -> float:
    """Weighted composite of expected_loss/P90/CVaR -- expected_loss is the
    central estimate so it carries the most weight, P90 and CVaR pull the
    score up for candidates whose tail risk is disproportionately worse
    than their average case, even if their expected_loss looks fine."""

    expected_loss = float(sim.expected_loss or 0)
    p90 = float(sim.p90 or 0)
    cvar = float(sim.cvar or 0)
    return 0.5 * expected_loss + 0.3 * p90 + 0.2 * cvar


def _feasibility_penalty(candidate: ResponseCandidate) -> float:
    """0 for 가능 (no penalty). 조건부 gets a penalty that grows with the
    number of preconditions still outstanding -- more preconditions means
    more can go wrong before this candidate is actually executable, so two
    조건부 candidates with the same risk score are not treated as equally
    ready. 불가능 candidates are never passed into rank_candidates at all
    (see build_decision_package), so they are not handled here -- if one
    ever slipped through, an infinite penalty pushes it last rather than
    silently ranking it as if it were viable."""

    if candidate.validation_status == "가능":
        return 0.0
    if candidate.validation_status == "조건부":
        return 0.15 + 0.05 * len(candidate.preconditions or [])
    return float("inf")


# Concern-level -> penalty weight for the 다중 관점 교차검증 (multi-perspective
# cross-review, app/services/candidate_review.py) signal. Values chosen to
# sit in the same rough range as _feasibility_penalty's 조건부 base (0.15) so
# neither penalty structurally dominates the other: "low" contributes
# nothing, "medium" is a mild nudge, "high" is a much larger penalty than
# any feasibility penalty a merely-조건부 candidate could accumulate.
REVIEW_CONCERN_PENALTY_WEIGHTS: dict[str, float] = {"low": 0.0, "medium": 0.2, "high": 0.5}


def _review_penalty(reviews_by_lens: dict[str, CandidateReview] | None) -> float:
    """Cross-review penalty derived from the 3 independent lens reviews
    (cost/feasibility/risk -- app/services/candidate_review.py). Returns 0
    when there are no reviews at all (candidate never reviewed, or review
    stage not yet run for this incident) -- never an error, so ranking a
    pre-existing incident with no cross-review history degrades gracefully.

    Deliberately MAX-based across the 3 lenses, not an average: if even one
    lens (say, risk) is genuinely alarmed (concern_level='high') while the
    other two are calm ('low'), an average would work out to roughly
    (0.5 + 0 + 0)/3 ≈ 0.17 -- barely above a single 'medium' lens, and easily
    swamped by the rest of the composite score. That would silently defeat
    the entire point of asking 3 *independent* lenses: one alarmed
    perspective would get diluted away by two calm ones instead of being
    heard. Taking the max instead means the candidate's whole composite_score
    reflects the single worst independent concern raised about it -- a
    reviewer looking only at the ranking still sees that *something* is
    seriously wrong, even if two of the three lenses saw nothing."""

    if not reviews_by_lens:
        return 0.0
    return max(
        REVIEW_CONCERN_PENALTY_WEIGHTS.get(review.concern_level, 0.0)
        for review in reviews_by_lens.values()
    )


def rank_candidates(
    pairs: list[tuple[ResponseCandidate, SimulationResult]],
    reviews_by_candidate: dict[int, dict[str, CandidateReview]] | None = None,
) -> list[dict[str, Any]]:
    """Ranks executable single-or-combined response candidates (baseline
    included) by a composite score, ascending (rank 1 = lowest composite
    risk). `pairs` must already be filtered to candidates that actually
    have a simulation result -- callers must exclude anything constraint-
    validation marked 불가능 or that was never simulated for any other
    reason (ARCHITECTURE.md §4.4: "시뮬레이션 결과가 없는 후보를 최적화 대상에
    넣지 않는다"); this function does not re-check that itself so it stays
    a pure ranking function over whatever it is handed.

    `reviews_by_candidate` maps candidate_id -> {lens: latest CandidateReview}
    (see CandidateReviewRepository.latest_by_lens_for_candidate) -- optional
    and defaults to "no reviews for anyone" so callers that have not run the
    다중 관점 교차검증 stage yet (or candidates it has no data for) still get
    a normal ranking with review_penalty=0, never an error.

    The review penalty is combined with the feasibility penalty the same
    way `_feasibility_penalty` was already being combined with risk before
    this feature existed: summed together *inside* the same
    `(1 + ...)` multiplier, rather than as its own separate multiplicative
    factor. This keeps both penalties proportional to the candidate's own
    risk_score (a candidate with near-zero risk stays near zero even with a
    'high' review concern -- the review flags a *relative* concern, not an
    absolute cost) and lets them compound simply by addition when a
    candidate happens to carry both a feasibility penalty (조건부) and a
    review penalty (a concerned lens) at the same time, instead of one
    penalty overriding or being swallowed by the other."""

    reviews_by_candidate = reviews_by_candidate or {}

    scored: list[dict[str, Any]] = []
    for candidate, sim in pairs:
        risk = _risk_score(sim)
        feasibility_penalty = _feasibility_penalty(candidate)
        review_penalty = _review_penalty(reviews_by_candidate.get(candidate.id))
        composite = risk * (1 + feasibility_penalty + review_penalty)
        scored.append(
            {
                "candidate_id": candidate.id,
                "candidate_type": candidate.candidate_type,
                "description": candidate.description,
                "start_time_variant": candidate.start_time_variant,
                "validation_status": candidate.validation_status,
                "preconditions": candidate.preconditions,
                "expected_loss": _to_float(sim.expected_loss),
                "p90": _to_float(sim.p90),
                "cvar": _to_float(sim.cvar),
                "risk_score": risk,
                "feasibility_penalty": feasibility_penalty,
                "review_penalty": review_penalty,
                "composite_score": composite,
            }
        )

    scored.sort(key=lambda item: item["composite_score"])
    for i, item in enumerate(scored, start=1):
        item["rank"] = i
    return scored


# ------------------------------------------------------------------
# Section builders -- one per §5.1 item, each always returning a
# structurally-present (possibly empty) value.
# ------------------------------------------------------------------


def _pair_summary(pair: tuple[ResponseCandidate, SimulationResult] | None) -> dict[str, Any] | None:
    if pair is None:
        return None
    candidate, sim = pair
    return {
        "candidate_id": candidate.id,
        "candidate_type": candidate.candidate_type,
        "description": candidate.description,
        "start_time_variant": candidate.start_time_variant,
        "expected_loss": _to_float(sim.expected_loss),
        "p90": _to_float(sim.p90),
        "cvar": _to_float(sim.cvar),
    }


def _causal_path(nodes: list[ImpactDagNode], edges: list[ImpactDagEdge]) -> dict[str, Any]:
    nodes_by_id = {n.id: n for n in nodes}
    return {
        "nodes": [
            {
                "node_key": n.node_key,
                "label": n.label,
                "affected_target": n.affected_target,
                "expected_time": n.expected_time,
                "basis": n.basis,
                "responsible_party": n.responsible_party,
                "uncertainty": n.uncertainty,
            }
            for n in nodes
        ],
        "edges": [
            {
                "from_node_key": nodes_by_id[e.from_node_id].node_key,
                "to_node_key": nodes_by_id[e.to_node_id].node_key,
                "basis": e.basis,
            }
            for e in edges
            if e.from_node_id in nodes_by_id and e.to_node_id in nodes_by_id
        ],
    }


def _group_latest_reviews_by_candidate(
    reviews: list[CandidateReview],
) -> dict[int, dict[str, CandidateReview]]:
    """Groups a flat, ascending-by-created_at list of candidate_reviews rows
    (as returned by CandidateReviewRepository.for_incident) into
    {candidate_id: {lens: latest CandidateReview}} -- since the list is
    ascending, later rows simply overwrite earlier ones per (candidate_id,
    lens), which is exactly "the most recent row per lens" without a
    second query per candidate (mirrors
    CandidateReviewRepository.latest_by_lens_for_candidate, but batched
    across every candidate of the incident in one pass)."""

    by_candidate: dict[int, dict[str, CandidateReview]] = {}
    for review in reviews:
        by_candidate.setdefault(review.candidate_id, {})[review.lens] = review
    return by_candidate


def _cross_perspective_reviews_section(
    all_candidates: list[ResponseCandidate],
    reviews_by_candidate: dict[int, dict[str, CandidateReview]],
) -> dict[str, Any]:
    """다중 관점 교차검증 결과를 후보별로 그대로(verbatim) 노출한다 -- 담당자가
    "왜 이 순위가 나왔는가"를 감사할 수 있도록. 후보에 리뷰가 아직 없으면(리뷰
    단계를 아직 실행하지 않은 기존 사건 등) 빈 reviews와 review_penalty=0으로
    표시할 뿐, 이 섹션 생성 자체가 실패하지 않는다. 이 섹션의 어떤 문구도 특정
    대응안이 정답이라고 단정하지 않는다 -- 우려사항을 노출할 뿐이다."""

    by_candidate: dict[str, Any] = {}
    for candidate in all_candidates:
        lens_reviews = reviews_by_candidate.get(candidate.id, {})
        by_candidate[str(candidate.id)] = {
            "reviews": {
                lens: {
                    "concern_level": review.concern_level,
                    "comment": review.comment,
                    "flags": list(review.flags or []),
                    "reviewed_at": review.created_at,
                }
                for lens, review in lens_reviews.items()
            },
            "review_penalty": _review_penalty(lens_reviews),
        }

    return {
        "note": (
            "각 대응안에 대한 비용(cost)/실행가능성(feasibility)/리스크(risk) 3개 독립 관점의 "
            "우려사항이다. 특정 대응안이 정답이라고 단정하지 않으며, ranked_candidates의 "
            "review_penalty로만 참고된다. 리뷰가 없는 후보는 review 단계가 아직 실행되지 않았음을 "
            "의미할 뿐, 우려사항이 없다는 뜻이 아니다."
        ),
        "by_candidate": by_candidate,
    }


@dataclass
class _CandidateBundle:
    """One incident's candidates partitioned by whether they have a latest
    simulation result -- computed once and reused by every section
    builder below rather than re-querying per section."""

    all_candidates: list[ResponseCandidate]
    with_sim: list[tuple[ResponseCandidate, SimulationResult]]
    without_sim: list[ResponseCandidate]


def _load_candidate_bundle(db: Session, incident_id: int) -> _CandidateBundle:
    candidate_repo = ResponseCandidateRepository(db)
    sim_repo = SimulationResultRepository(db)

    all_candidates = candidate_repo.for_incident(incident_id)
    with_sim: list[tuple[ResponseCandidate, SimulationResult]] = []
    without_sim: list[ResponseCandidate] = []
    for c in all_candidates:
        latest = sim_repo.latest_for_candidate(c.id)
        if latest is not None:
            with_sim.append((c, latest))
        else:
            without_sim.append(c)

    return _CandidateBundle(all_candidates=all_candidates, with_sim=with_sim, without_sim=without_sim)


def build_decision_package(db: Session, incident_id: int) -> DecisionPackage:
    """Assembles and persists (append-only -- always a new row) one
    decision package for `incident_id`, built from whatever candidates /
    simulation results / Impact DAG exist for it *at the moment this is
    called*. Raises IncidentNotFoundError / IncidentNotEligibleError (via
    ensure_snapshot_and_dag) for the API layer to translate into 404/409,
    same as every other endpoint in this pipeline.

    Handles the "모든 후보가 제외된 극단 케이스" (DoD case 2) gracefully: if
    only baseline has a simulation result (or even if nothing does at
    all), every §5.1 section below is still built and present in the
    package -- just with empty/None content where there is genuinely
    nothing to report, never a missing key.
    """

    # ensure_snapshot_and_dag both validates the incident (404/409) and is
    # the only way to obtain the snapshot this package's DAG/freshness data
    # is pinned to -- a no-op read if one already exists (lazy-create
    # contract, same as every sibling endpoint in this codebase).
    snapshot: OperationalSnapshot = ensure_snapshot_and_dag(db, incident_id)

    node_repo = ImpactDagNodeRepository(db)
    edge_repo = ImpactDagEdgeRepository(db)
    nodes = node_repo.for_snapshot(snapshot.id)
    edges = edge_repo.for_snapshot(snapshot.id)

    bundle = _load_candidate_bundle(db, incident_id)

    # ---- 다중 관점 교차검증 (cross_perspective_reviews) ----
    # Missing entirely (pre-existing incidents, or the review stage simply
    # hasn't run yet) degrades gracefully: _group_latest_reviews_by_candidate
    # over an empty list yields {}, so every candidate below just shows
    # review_penalty=0 / no reviews rather than raising.
    all_reviews = CandidateReviewRepository(db).for_incident(incident_id)
    reviews_by_candidate = _group_latest_reviews_by_candidate(all_reviews)

    # ---- 1. expected_loss_p90_cvar ----
    expected_loss_p90_cvar = {
        str(c.id): {
            "candidate_type": c.candidate_type,
            "description": c.description,
            "expected_loss": _to_float(sim.expected_loss),
            "p90": _to_float(sim.p90),
            "cvar": _to_float(sim.cvar),
        }
        for c, sim in bundle.with_sim
    }

    # ---- 2. now_vs_6h_vs_no_action ----
    baseline_pair = next(
        (pair for pair in bundle.with_sim if pair[0].candidate_type == BASELINE_CANDIDATE_TYPE), None
    )
    now_pair = next(
        (
            pair
            for pair in bundle.with_sim
            if pair[0].candidate_type != BASELINE_CANDIDATE_TYPE
            and pair[0].start_time_variant in NOW_START_TIME_VARIANTS
        ),
        None,
    )
    plus_6h_pair = next(
        (pair for pair in bundle.with_sim if pair[0].start_time_variant == PLUS_6H_START_TIME_VARIANT), None
    )
    now_vs_6h_vs_no_action = {
        "no_action": _pair_summary(baseline_pair),
        "now": _pair_summary(now_pair),
        "plus_6h": _pair_summary(plus_6h_pair),
    }

    # ---- 3. causal_path ----
    causal_path = _causal_path(nodes, edges)

    # ---- 4. data_and_documents_used ----
    data_and_documents_used = {
        "operational_assumptions": list(snapshot.assumptions or []),
        "data_version": snapshot.data_version,
        "scenario_version": snapshot.scenario_version,
        "reference_document_ids_by_candidate": {
            str(c.id): list(c.reference_document_ids or []) for c in bundle.all_candidates
        },
    }

    # ---- 5. fact_inference_assumption ----
    fact_inference_assumption = {
        str(c.id): {"fact": sim.fact, "inference": sim.inference, "assumption": sim.assumption}
        for c, sim in bundle.with_sim
    }

    # ---- 6. freshness_and_coverage ----
    freshness_and_coverage = {
        "quality_mode": snapshot.quality_mode,
        "freshness_seconds": snapshot.freshness_seconds,
        "coverage_ratio": _to_float(snapshot.coverage_ratio),
    }

    # ---- 7. key_sensitivity_variables ----
    key_sensitivity_variables = {str(c.id): list(sim.sensitivity_variables or []) for c, sim in bundle.with_sim}

    # ---- 8. feasibility_and_exclusion (every candidate, simulated or not) ----
    feasibility_and_exclusion: dict[str, Any] = {}
    for c, _sim in bundle.with_sim:
        feasibility_and_exclusion[str(c.id)] = {
            "validation_status": c.validation_status,
            "exclusion_category": c.exclusion_category,
            "exclusion_detail": c.exclusion_detail,
            "preconditions": list(c.preconditions or []),
            "has_simulation_result": True,
        }
    for c in bundle.without_sim:
        feasibility_and_exclusion[str(c.id)] = {
            "validation_status": c.validation_status,
            "exclusion_category": c.exclusion_category,
            "exclusion_detail": (
                c.exclusion_detail
                or "시뮬레이션 대상에서 제외됨 (제약 검증에서 불가능 처리되었거나 아직 시뮬레이션되지 않음)"
            ),
            "preconditions": list(c.preconditions or []),
            "has_simulation_result": False,
        }

    # ---- 9. confidence_and_uncertainty ----
    confidence_and_uncertainty = {}
    for c, sim in bundle.with_sim:
        expected_loss = _to_float(sim.expected_loss)
        p90 = _to_float(sim.p90)
        cvar = _to_float(sim.cvar)
        confidence_and_uncertainty[str(c.id)] = {
            "confidence": _to_float(sim.confidence),
            "uncertainty_range": {
                "expected_loss": expected_loss,
                "p90": p90,
                "cvar": cvar,
                "p90_minus_expected_loss": (p90 - expected_loss) if p90 is not None and expected_loss is not None else None,
                "cvar_minus_p90": (cvar - p90) if cvar is not None and p90 is not None else None,
            },
        }

    # ---- 10. recommended_deadline ----
    deadline, deadline_detail = compute_recommended_deadline(nodes, edges)

    # ---- ranking (work item #2), now review_penalty-aware ----
    ranked = rank_candidates(bundle.with_sim, reviews_by_candidate)
    excluded_from_ranking = [
        {
            "candidate_id": c.id,
            "candidate_type": c.candidate_type,
            "description": c.description,
            "validation_status": c.validation_status,
            "exclusion_category": c.exclusion_category,
            "exclusion_detail": c.exclusion_detail,
            "reason": "시뮬레이션 결과가 없어 최적화/순위화 대상에서 제외됨",
        }
        for c in bundle.without_sim
    ]

    # ---- cross_perspective_reviews (다중 관점 교차검증, additional transparency) ----
    cross_perspective_reviews = _cross_perspective_reviews_section(bundle.all_candidates, reviews_by_candidate)

    package: dict[str, Any] = {
        "expected_loss_p90_cvar": expected_loss_p90_cvar,
        "now_vs_6h_vs_no_action": now_vs_6h_vs_no_action,
        "causal_path": causal_path,
        "data_and_documents_used": data_and_documents_used,
        "fact_inference_assumption": fact_inference_assumption,
        "freshness_and_coverage": freshness_and_coverage,
        "key_sensitivity_variables": key_sensitivity_variables,
        "feasibility_and_exclusion": feasibility_and_exclusion,
        "confidence_and_uncertainty": confidence_and_uncertainty,
        "recommended_deadline": {"deadline": deadline, "detail": deadline_detail},
        "ranked_candidates": {"ranked": ranked, "excluded_from_ranking": excluded_from_ranking},
        "cross_perspective_reviews": cross_perspective_reviews,
        "disclaimer": DISCLAIMER,
    }

    package = _json_safe(package)

    return DecisionPackageRepository(db).add(
        incident_id=incident_id,
        package=package,
        recommended_deadline=deadline,
    )
