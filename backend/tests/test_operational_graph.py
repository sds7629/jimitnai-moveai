"""Tests for the operational-graph agent (agents/operational-graph.md).

Covers the DoD's minimum 3 cases plus edge cases:
  1. Normal snapshot + Impact DAG generation for a newly validated incident.
  2. append-only behaviour under lazy-create + explicit recompute: calling
     ensure_snapshot_and_dag twice must not add a row; force_recompute=True
     must append a new row while leaving the old one untouched; and the
     already-seeded scenario incidents (db/init/003-seed-scenarios.sql) must
     be picked up as "already has a snapshot" rather than duplicated.
  3. Data-quality gate: missing required affected_targets (or an incident
     type outside the 3 seed scenarios) must produce quality_mode='limited'
     without aborting the analysis (a DAG is still produced).

Plus: incident-not-found -> 404, incident not status='유효' -> 409.

Hits the real app + real Postgres, matching the existing test style (no
DB mocking) — see test_incident_intake.py / test_seed_scenarios.py.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.impact_dag import ImpactDagEdgeRepository, ImpactDagNodeRepository
from app.repositories.operational_snapshots import OperationalSnapshotRepository
from app.services.operational_graph import (
    IncidentNotEligibleError,
    IncidentNotFoundError,
    ensure_snapshot_and_dag,
)

client = TestClient(app)

# Same isolation technique as test_incident_intake.py: a per-run suffix on
# every test-owned location keeps the 12h duplicate-detection window from
# treating two different test runs' incidents as duplicates of each other.
_RUN_ID = uuid.uuid4().hex[:8]


def _loc(base: str) -> str:
    return f"{base} ({_RUN_ID})"


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _create_incident(payload: dict) -> dict:
    resp = client.post("/incidents", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _full_congestion_payload(location_suffix: str) -> dict:
    occurred_at = datetime.now(timezone.utc) - timedelta(days=2)
    return {
        "type": "항만 적체",
        "location": _loc(location_suffix),
        "occurred_at": _iso(occurred_at),
        "affected_targets": {
            "containers": ["CTN-OG-1"],
            "parts": ["PT-OG-ENGINE"],
            "production_orders": ["PO-OG-1"],
            "customers": ["Dealer-OG-1"],
        },
    }


# ------------------------------------------------------------------
# 1. Normal snapshot + DAG generation
# ------------------------------------------------------------------


def test_normal_snapshot_and_dag_generated_for_valid_incident():
    incident = _create_incident(_full_congestion_payload("정상생성테스트"))
    incident_id = incident["id"]
    assert incident["status"] == "유효"

    snap_resp = client.get(f"/incidents/{incident_id}/snapshots/latest")
    assert snap_resp.status_code == 200, snap_resp.text
    snap = snap_resp.json()

    assert snap["incident_id"] == incident_id
    assert snap["data_version"] == "v1"
    assert snap["scenario_version"] == "scenario-congestion-v1"
    assert snap["quality_mode"] == "normal"
    assert snap["coverage_ratio"] == 1.0
    # incident-intake produced no assumptions here (nothing missing), but
    # this module must always add its own no-real-time-integration note.
    assert any("ASSUMPTION" in a for a in snap["assumptions"])
    assert "PT-OG-ENGINE" in snap["operational_state"]["inventory"]
    assert "PO-OG-1" in snap["operational_state"]["production"]
    assert "CTN-OG-1" in snap["operational_state"]["transport"]

    dag_resp = client.get(f"/incidents/{incident_id}/impact-dag")
    assert dag_resp.status_code == 200, dag_resp.text
    dag = dag_resp.json()

    assert dag["snapshot_id"] == snap["id"]
    assert dag["data_version"] == "v1"
    assert len(dag["nodes"]) == 4
    assert len(dag["edges"]) == 3

    node_keys = [n["node_key"] for n in dag["nodes"]]
    assert node_keys == ["trigger", "container_release_delay", "inventory_depletion", "production_halt"]

    # No unfounded nodes: every node must carry its evidentiary fields.
    for node in dag["nodes"]:
        assert node["affected_target"]
        assert node["expected_time"]
        assert node["basis"]
        assert node["responsible_party"]
        assert node["uncertainty"] in ("low", "medium", "high")

    # Edges form the linear chain n1->n2->n3->n4, each with a basis.
    nodes_by_id = {n["id"]: n["node_key"] for n in dag["nodes"]}
    edge_pairs = [(nodes_by_id[e["from_node_id"]], nodes_by_id[e["to_node_id"]]) for e in dag["edges"]]
    assert edge_pairs == [
        ("trigger", "container_release_delay"),
        ("container_release_delay", "inventory_depletion"),
        ("inventory_depletion", "production_halt"),
    ]
    assert all(e["basis"] for e in dag["edges"])


def test_snapshot_generation_works_for_all_3_seed_scenario_types():
    payloads = [
        (
            "항만 파업",
            {
                "containers": ["CTN-OG-STRIKE"],
                "parts": ["PT-OG-BATTERY"],
                "production_orders": ["PO-OG-STRIKE"],
                "customers": ["Dealer-OG-2"],
            },
            "strike",
            "handling_customs_halt",
            "production_halt",
        ),
        (
            "관세 규정 변경",
            {
                "containers": ["CTN-OG-TARIFF"],
                "parts": ["PT-OG-CHIP"],
                "production_orders": ["PO-OG-TARIFF"],
                "customers": ["Dealer-OG-3"],
            },
            "tariff",
            "customs_clearance_delay",
            "production_impact",
        ),
    ]
    for type_, targets, slug, secondary_key, production_key in payloads:
        occurred_at = datetime.now(timezone.utc) - timedelta(days=2)
        incident = _create_incident(
            {
                "type": type_,
                "location": _loc(f"시나리오테스트-{slug}"),
                "occurred_at": _iso(occurred_at),
                "affected_targets": targets,
            }
        )
        dag = client.get(f"/incidents/{incident['id']}/impact-dag").json()
        assert [n["node_key"] for n in dag["nodes"]] == [
            "trigger",
            secondary_key,
            "inventory_depletion",
            production_key,
        ]
        assert dag["scenario_version"] == f"scenario-{slug}-v1"


# ------------------------------------------------------------------
# 2. append-only: idempotent lazy-create + explicit recompute
# ------------------------------------------------------------------


def test_ensure_snapshot_and_dag_is_idempotent(db_session):
    incident = _create_incident(_full_congestion_payload("재계산idempotent테스트"))
    incident_id = incident["id"]

    first = ensure_snapshot_and_dag(db_session, incident_id)
    second = ensure_snapshot_and_dag(db_session, incident_id)

    assert first.id == second.id
    history = OperationalSnapshotRepository(db_session).history_for_incident(incident_id)
    assert len(history) == 1


def test_force_recompute_appends_new_row_without_touching_old_one(db_session):
    incident = _create_incident(_full_congestion_payload("강제재계산테스트"))
    incident_id = incident["id"]

    original = ensure_snapshot_and_dag(db_session, incident_id)
    recomputed = ensure_snapshot_and_dag(db_session, incident_id, force_recompute=True)

    assert recomputed.id != original.id
    assert recomputed.data_version == "v2"
    assert original.data_version == "v1"

    history = OperationalSnapshotRepository(db_session).history_for_incident(incident_id)
    assert len(history) == 2
    # The old row is exactly as it was -- still present, unchanged version.
    ids = {row.id for row in history}
    assert original.id in ids
    assert recomputed.id in ids

    # Each snapshot has its own DAG; the old snapshot's DAG must still exist.
    old_nodes = ImpactDagNodeRepository(db_session).for_snapshot(original.id)
    new_nodes = ImpactDagNodeRepository(db_session).for_snapshot(recomputed.id)
    assert len(old_nodes) == 4
    assert len(new_nodes) == 4
    old_edges = ImpactDagEdgeRepository(db_session).for_snapshot(original.id)
    assert len(old_edges) == 3


def test_seeded_incident_reuses_existing_snapshot_without_duplicating(db_session, seeded_incident_id):
    history_before = OperationalSnapshotRepository(db_session).history_for_incident(seeded_incident_id)
    assert len(history_before) == 1  # seeded directly by db/init/003-seed-scenarios.sql

    snapshot = ensure_snapshot_and_dag(db_session, seeded_incident_id)

    assert snapshot.id == history_before[0].id
    history_after = OperationalSnapshotRepository(db_session).history_for_incident(seeded_incident_id)
    assert len(history_after) == 1


# ------------------------------------------------------------------
# 3. Data quality gate -> limited mode, analysis still proceeds
# ------------------------------------------------------------------


def test_limited_mode_when_required_affected_targets_missing():
    occurred_at = datetime.now(timezone.utc) - timedelta(days=2)
    incident = _create_incident(
        {
            "type": "항만 적체",
            "location": _loc("제한모드-일부누락"),
            "occurred_at": _iso(occurred_at),
            # only parts provided -- production_orders/containers missing
            "affected_targets": {"parts": ["PT-OG-PARTIAL"]},
        }
    )

    snap = client.get(f"/incidents/{incident['id']}/snapshots/latest").json()

    assert snap["quality_mode"] == "limited"
    assert snap["coverage_ratio"] < 1.0
    assert any("누락" in a for a in snap["assumptions"])

    # Analysis is not aborted -- a full DAG is still produced.
    dag = client.get(f"/incidents/{incident['id']}/impact-dag").json()
    assert len(dag["nodes"]) == 4
    assert len(dag["edges"]) == 3


def test_limited_mode_when_incident_type_unmatched_to_any_seed_scenario():
    occurred_at = datetime.now(timezone.utc) - timedelta(days=2)
    incident = _create_incident(
        {
            "type": "알수없는 신규 사건유형",
            "location": _loc("제한모드-유형불일치"),
            "occurred_at": _iso(occurred_at),
            "affected_targets": {
                "containers": ["CTN-OG-UNK"],
                "parts": ["PT-OG-UNK"],
                "production_orders": ["PO-OG-UNK"],
                "customers": ["Dealer-OG-UNK"],
            },
        }
    )

    snap = client.get(f"/incidents/{incident['id']}/snapshots/latest").json()

    # Even with full coverage, an unrecognized scenario type is always
    # limited -- there is no real operational data source for it at all.
    assert snap["quality_mode"] == "limited"
    assert snap["coverage_ratio"] == 1.0
    assert any("매칭되지 않아" in a for a in snap["assumptions"])

    dag = client.get(f"/incidents/{incident['id']}/impact-dag").json()
    assert [n["node_key"] for n in dag["nodes"]] == [
        "trigger",
        "operational_disruption",
        "inventory_depletion",
        "production_impact",
    ]


# ------------------------------------------------------------------
# Not-found / not-eligible edge cases
# ------------------------------------------------------------------


def test_snapshot_endpoint_404s_for_unknown_incident():
    resp = client.get("/incidents/999999999/snapshots/latest")
    assert resp.status_code == 404


def test_impact_dag_endpoint_404s_for_unknown_incident():
    resp = client.get("/incidents/999999999/impact-dag")
    assert resp.status_code == 404


def test_duplicate_incident_is_not_eligible_for_snapshot(db_session):
    occurred_at = datetime.now(timezone.utc) - timedelta(hours=1)
    base_payload = {
        "type": "항만 적체",
        "location": _loc("스냅샷대상아님-중복"),
        "occurred_at": _iso(occurred_at),
        "affected_targets": {"containers": ["CTN-OG-DUP"]},
    }
    first = _create_incident(base_payload)
    second_payload = {**base_payload, "occurred_at": _iso(occurred_at + timedelta(minutes=30))}
    second = _create_incident(second_payload)
    assert second["status"] == "중복"

    resp = client.get(f"/incidents/{second['id']}/snapshots/latest")
    assert resp.status_code == 409

    with pytest.raises(IncidentNotEligibleError):
        ensure_snapshot_and_dag(db_session, second["id"])

    with pytest.raises(IncidentNotFoundError):
        ensure_snapshot_and_dag(db_session, 999999999)
