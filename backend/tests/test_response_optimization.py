"""Tests for the response-optimization agent (agents/response-optimization.md)
-- app/services/response_optimization.py + GET /incidents/{id}/decision-package.

Covers the DoD's minimum 3 cases plus edge cases:
  1. Normal package generation: all 10 §5.1 items are present and filled
     for an incident that went through the full simulate pipeline.
  2. Extreme case: every non-baseline candidate is excluded (불가능), only
     baseline has a simulation result -- the package must still be built
     with all 10 items present, ranked_candidates containing only baseline,
     and the excluded candidates' reasons preserved.
  3. Decision-deadline reverse-calculation (`compute_recommended_deadline`)
     verified directly against hand-built Impact DAG node/edge objects,
     independent of the DB/simulate pipeline.

Plus: ranking is multi-criteria (not a single-field sort), candidates with
no simulation result are never ranked, the GET endpoint's re-run/re-cache
policy (reuse unless a newer simulation exists), and 404 for an unknown
incident.

No real LLM/embedding call is exercised -- get_llm_provider is monkeypatched
in both service modules the pipeline depends on, same pattern as
tests/test_simulate_api.py.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.impact_dag import ImpactDagEdge, ImpactDagNode
from app.repositories.decision_packages import DecisionPackageRepository
from app.repositories.response_candidates import ResponseCandidateRepository
from app.services.constraint_validation import validate_candidates
from app.services.operational_graph import IncidentNotFoundError
from app.services.response_design import generate_candidates
from app.services.response_optimization import (
    build_decision_package,
    compute_recommended_deadline,
    rank_candidates,
)
from app.services.simulation import simulate_candidates

client = TestClient(app)
_RUN_ID = uuid.uuid4().hex[:8]


@pytest.fixture(autouse=True)
def _fake_llm_and_embeddings(monkeypatch):
    monkeypatch.setattr("app.rag.search.embed_text", lambda _text: [0.0] * 768)
    monkeypatch.setattr(
        "app.services.response_design.get_llm_provider", lambda: _FakeCandidateProvider()
    )
    monkeypatch.setattr("app.services.simulation.get_llm_provider", lambda: _FakeSimProvider())


class _FakeCandidateProvider:
    def generate(self, prompt, *, system=None, temperature=0.7):
        return json.dumps(
            {
                "candidates": [
                    {
                        "response_category": "컨테이너 우선반출",
                        "candidate_type": "단일",
                        "description": "컨테이너 우선 반출 슬롯 확보",
                        "preconditions": [],
                        "start_time_variant": "now",
                        "reference_document_ids": [],
                    },
                    {
                        "response_category": "고객출고우선순위",
                        "candidate_type": "단일",
                        "description": "고객 우선순위 조정 (지연 착수)",
                        "preconditions": [],
                        "start_time_variant": "+6h",
                        "reference_document_ids": [],
                    },
                ]
            }
        )


def _sim_json(expected_loss: float = 1_000_000) -> str:
    return json.dumps(
        {
            "expected_loss": expected_loss,
            "p90": expected_loss * 2,
            "cvar": expected_loss * 2.5,
            "confidence": 0.7,
            "sensitivity_variables": ["안전재고 소진 속도"],
            "fact": {"qty": 480},
            "inference": {"depletion_hours": 14},
            "assumption": {"consumption_rate": "steady"},
        }
    )


class _FakeSimProvider:
    def __init__(self, expected_loss: float = 1_000_000):
        self._expected_loss = expected_loss

    def generate(self, prompt, *, system=None, temperature=0.7):
        return _sim_json(self._expected_loss)


def _loc(base: str) -> str:
    return f"{base} ({_RUN_ID})"


def _create_incident(type_: str, location: str) -> dict:
    unique_container = f"CTN-OPT-{uuid.uuid4().hex[:8]}"
    occurred_at = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "type": type_,
        "location": _loc(location),
        "occurred_at": occurred_at.isoformat(),
        "affected_targets": {
            "containers": [unique_container],
            "parts": ["PT-OPT-1"],
            "production_orders": ["PO-OPT-1"],
            "customers": ["Dealer-OPT-1"],
        },
    }
    resp = client.post("/incidents", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ------------------------------------------------------------------
# 1. Normal package generation -- all 10 §5.1 items present and filled
# ------------------------------------------------------------------

REQUIRED_PACKAGE_KEYS = [
    "expected_loss_p90_cvar",
    "now_vs_6h_vs_no_action",
    "causal_path",
    "data_and_documents_used",
    "fact_inference_assumption",
    "freshness_and_coverage",
    "key_sensitivity_variables",
    "feasibility_and_exclusion",
    "confidence_and_uncertainty",
    "recommended_deadline",
]


def test_decision_package_has_all_10_items_filled():
    incident = _create_incident("항만 적체", "정상패키지")

    resp = client.post(f"/incidents/{incident['id']}/simulate")
    assert resp.status_code == 200, resp.text

    pkg_resp = client.get(f"/incidents/{incident['id']}/decision-package")
    assert pkg_resp.status_code == 200, pkg_resp.text
    body = pkg_resp.json()

    assert body["incident_id"] == incident["id"]
    assert body["recommended_deadline"] is not None
    package = body["package"]

    for key in REQUIRED_PACKAGE_KEYS:
        assert key in package, f"missing §5.1 item: {key}"

    # 1. expected_loss_p90_cvar -- at least baseline + the LLM candidates
    assert len(package["expected_loss_p90_cvar"]) >= 2

    # 2. now vs 6h vs no-action -- all three slots present (may be None but
    #    the key must exist), and here all three are actually populated
    #    since the fake candidate provider always emits a now/+6h pair.
    comparison = package["now_vs_6h_vs_no_action"]
    assert set(comparison.keys()) == {"no_action", "now", "plus_6h"}
    assert comparison["no_action"] is not None
    assert comparison["now"] is not None
    assert comparison["plus_6h"] is not None

    # 3. causal path -- node label order + basis
    causal = package["causal_path"]
    assert [n["node_key"] for n in causal["nodes"]] == [
        "trigger",
        "container_release_delay",
        "inventory_depletion",
        "production_halt",
    ]
    assert all(n["basis"] for n in causal["nodes"])
    assert len(causal["edges"]) == 3

    # 4. data/documents used
    assert package["data_and_documents_used"]["operational_assumptions"]
    assert "reference_document_ids_by_candidate" in package["data_and_documents_used"]

    # 5. FACT/INFERENCE/ASSUMPTION carried through verbatim
    for entry in package["fact_inference_assumption"].values():
        assert entry["fact"] and entry["inference"] and entry["assumption"]

    # 6. freshness/coverage
    freshness = package["freshness_and_coverage"]
    assert freshness["quality_mode"] in ("normal", "limited")
    assert freshness["freshness_seconds"] is not None
    assert freshness["coverage_ratio"] is not None

    # 7. sensitivity variables
    assert all(package["key_sensitivity_variables"].values())

    # 8. feasibility/exclusion -- present for every candidate, not just
    #    simulated ones
    candidates_resp = client.get(f"/incidents/{incident['id']}/candidates").json()
    assert len(package["feasibility_and_exclusion"]) == len(candidates_resp["candidates"])

    # 9. confidence/uncertainty
    for entry in package["confidence_and_uncertainty"].values():
        assert entry["confidence"] is not None
        assert entry["uncertainty_range"]["p90_minus_expected_loss"] is not None

    # 10. recommended deadline detail
    deadline_section = package["recommended_deadline"]
    assert deadline_section["deadline"] is not None
    assert deadline_section["detail"]["irreversible_node_key"] == "production_halt"

    # Ranking deliverable + no "this is the answer" language anywhere.
    ranked = package["ranked_candidates"]["ranked"]
    assert len(ranked) >= 2
    assert [item["rank"] for item in ranked] == list(range(1, len(ranked) + 1))
    # The disclaimer must explicitly deny declaring any candidate "the
    # answer", never assert it as fact.
    assert "정답으로 단정하지 않습니다" in package["disclaimer"]


# ------------------------------------------------------------------
# 2. Extreme case: all non-baseline candidates excluded -> baseline only
# ------------------------------------------------------------------


def test_decision_package_handles_all_candidates_excluded_except_baseline(db_session):
    incident = _create_incident("항만 적체", "전부제외")

    asyncio.run(generate_candidates(db_session, incident["id"]))
    validate_candidates(db_session, incident["id"])

    candidate_repo = ResponseCandidateRepository(db_session)
    all_candidates = candidate_repo.for_incident(incident["id"])
    baseline = next(c for c in all_candidates if c.candidate_type == "baseline")

    for c in all_candidates:
        if c.candidate_type != "baseline":
            candidate_repo.update(
                c.id,
                validation_status="불가능",
                exclusion_category="자원부족",
                exclusion_detail="테스트로 강제 제외",
            )

    asyncio.run(simulate_candidates(db_session, incident["id"]))

    package_obj = build_decision_package(db_session, incident["id"])
    package = package_obj.package

    for key in REQUIRED_PACKAGE_KEYS:
        assert key in package

    ranked = package["ranked_candidates"]["ranked"]
    assert len(ranked) == 1
    assert ranked[0]["candidate_id"] == baseline.id
    assert ranked[0]["rank"] == 1

    excluded = package["ranked_candidates"]["excluded_from_ranking"]
    assert len(excluded) == len(all_candidates) - 1
    for entry in excluded:
        assert entry["validation_status"] == "불가능"
        assert entry["exclusion_detail"] == "테스트로 강제 제외"
        assert entry["reason"]

    # feasibility_and_exclusion still lists every candidate, simulated or not
    assert len(package["feasibility_and_exclusion"]) == len(all_candidates)
    for c in all_candidates:
        if c.candidate_type != "baseline":
            assert package["feasibility_and_exclusion"][str(c.id)]["has_simulation_result"] is False

    # now/6h/no-action comparison degrades gracefully (no non-baseline
    # simulated candidate exists to fill "now"/"plus_6h")
    comparison = package["now_vs_6h_vs_no_action"]
    assert comparison["no_action"] is not None
    assert comparison["now"] is None
    assert comparison["plus_6h"] is None


# ------------------------------------------------------------------
# 3. Decision-deadline reverse-calculation, independent of the DB
# ------------------------------------------------------------------


def _node(id_, key, label, expected_time, basis="test basis", affected_target="X"):
    return ImpactDagNode(
        id=id_,
        snapshot_id=1,
        node_key=key,
        label=label,
        affected_target=affected_target,
        expected_time=expected_time,
        basis=basis,
        responsible_party="test",
        uncertainty="medium",
    )


def _edge(id_, from_id, to_id, basis="edge basis"):
    return ImpactDagEdge(id=id_, snapshot_id=1, from_node_id=from_id, to_node_id=to_id, basis=basis)


def test_compute_recommended_deadline_uses_predecessor_of_production_halt():
    now = datetime.now(timezone.utc)
    n1 = _node(1, "trigger", "트리거", now)
    n2 = _node(2, "secondary", "2차 파급", now + timedelta(hours=2))
    n3 = _node(3, "inventory_depletion", "재고 소진", now + timedelta(hours=10))
    n4 = _node(4, "production_halt", "생산라인 중단", now + timedelta(hours=16))
    edges = [_edge(1, 1, 2), _edge(2, 2, 3), _edge(3, 3, 4)]

    deadline, detail = compute_recommended_deadline([n1, n2, n3, n4], edges)

    # Deadline must be the predecessor's (inventory_depletion) expected_time
    # -- not the irreversible node's own time, and not some fixed offset.
    assert deadline == n3.expected_time
    assert detail["irreversible_node_key"] == "production_halt"
    assert detail["deadline_basis_node_key"] == "inventory_depletion"
    assert "생산라인 중단" in detail["impact_if_exceeded"]


def test_compute_recommended_deadline_falls_back_to_inventory_depletion_when_no_production_node():
    now = datetime.now(timezone.utc)
    n1 = _node(1, "trigger", "트리거", now)
    n2 = _node(2, "secondary", "2차 파급", now + timedelta(hours=3))
    n3 = _node(3, "inventory_depletion", "재고 소진", now + timedelta(hours=12))
    edges = [_edge(1, 1, 2), _edge(2, 2, 3)]

    deadline, detail = compute_recommended_deadline([n1, n2, n3], edges)

    assert detail["irreversible_node_key"] == "inventory_depletion"
    assert deadline == n2.expected_time  # predecessor of inventory_depletion


def test_compute_recommended_deadline_returns_none_for_empty_dag():
    deadline, detail = compute_recommended_deadline([], [])
    assert deadline is None
    assert "note" in detail


# ------------------------------------------------------------------
# Ranking is multi-criteria, not a single-field sort
# ------------------------------------------------------------------


def test_ranking_considers_feasibility_not_just_expected_loss(db_session):
    """A 조건부 candidate's composite_score must be inflated above its raw
    risk_score by outstanding preconditions -- proving the ranking key
    factors in feasibility, not just expected_loss/P90/CVaR alone (a 가능
    candidate with an identical risk_score is not treated as equally
    ready as one with 3 preconditions still outstanding)."""

    incident = _create_incident("항만 적체", "다기준순위")
    asyncio.run(generate_candidates(db_session, incident["id"]))
    validate_candidates(db_session, incident["id"])

    candidate_repo = ResponseCandidateRepository(db_session)
    candidates = candidate_repo.for_incident(incident["id"])
    non_baseline = [c for c in candidates if c.candidate_type != "baseline"]
    assert len(non_baseline) >= 1
    target = non_baseline[0]
    candidate_repo.update(
        target.id,
        validation_status="조건부",
        preconditions=["승인 1", "승인 2", "승인 3"],
    )

    asyncio.run(simulate_candidates(db_session, incident["id"]))
    package_obj = build_decision_package(db_session, incident["id"])
    ranked = package_obj.package["ranked_candidates"]["ranked"]

    conditional_entry = next(item for item in ranked if item["candidate_id"] == target.id)
    assert conditional_entry["feasibility_penalty"] > 0
    assert conditional_entry["composite_score"] > conditional_entry["risk_score"]


def test_rank_candidates_never_includes_unsimulated_candidates():
    # Direct unit test of rank_candidates() over an empty pairs list (the
    # "nothing simulated at all" edge case) -- must not raise and must
    # return an empty ranking, never fabricate an entry.
    assert rank_candidates([]) == []


# ------------------------------------------------------------------
# GET endpoint: re-run/re-cache policy + 404
# ------------------------------------------------------------------


def test_decision_package_endpoint_reuses_cached_package_when_no_new_simulation():
    incident = _create_incident("항만 적체", "캐시재사용")
    client.post(f"/incidents/{incident['id']}/simulate")

    first = client.get(f"/incidents/{incident['id']}/decision-package").json()
    second = client.get(f"/incidents/{incident['id']}/decision-package").json()

    assert first["id"] == second["id"]  # same row reused, no duplicate append


def test_decision_package_endpoint_recomputes_after_new_simulation(db_session):
    incident = _create_incident("항만 적체", "재계산트리거")
    client.post(f"/incidents/{incident['id']}/simulate")
    first = client.get(f"/incidents/{incident['id']}/decision-package").json()

    # A fresh /simulate call appends new simulation_results rows (append-only
    # re-simulation, see app/services/simulation.py) -- the next GET must
    # not keep serving the now-stale first package.
    client.post(f"/incidents/{incident['id']}/simulate")
    second = client.get(f"/incidents/{incident['id']}/decision-package").json()

    assert second["id"] != first["id"]

    package_repo = DecisionPackageRepository(db_session)
    all_rows = [
        p for p in [package_repo.get(first["id"]), package_repo.get(second["id"])] if p is not None
    ]
    assert len(all_rows) == 2  # both rows still queryable -- append-only, old one untouched


def test_decision_package_endpoint_404s_for_unknown_incident():
    resp = client.get("/incidents/999999999/decision-package")
    assert resp.status_code == 404


def test_build_decision_package_raises_not_found_for_unknown_incident(db_session):
    with pytest.raises(IncidentNotFoundError):
        build_decision_package(db_session, 999999999)
