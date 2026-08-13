import pytest
from sqlalchemy import text

from app.repositories.seed_scenarios import SeedScenarioRepository

SCENARIO_KEYS = ["적체", "파업", "관세"]


@pytest.mark.parametrize("key", SCENARIO_KEYS)
def test_seed_scenario_exists_with_incident_and_snapshot(db_session, key):
    row = db_session.execute(
        text("SELECT scenario_key, incident_id, snapshot_id FROM seed_scenarios WHERE scenario_key = :k"),
        {"k": key},
    ).one_or_none()
    assert row is not None, f"seed scenario {key} missing"
    assert row.incident_id is not None
    assert row.snapshot_id is not None


@pytest.mark.parametrize("key", SCENARIO_KEYS)
def test_seed_scenario_dag_has_min_nodes_and_edges(db_session, key):
    snapshot_id = db_session.execute(
        text("SELECT snapshot_id FROM seed_scenarios WHERE scenario_key = :k"), {"k": key}
    ).scalar_one()
    node_count = db_session.execute(
        text("SELECT count(*) FROM impact_dag_nodes WHERE snapshot_id = :sid"), {"sid": snapshot_id}
    ).scalar_one()
    edge_count = db_session.execute(
        text("SELECT count(*) FROM impact_dag_edges WHERE snapshot_id = :sid"), {"sid": snapshot_id}
    ).scalar_one()
    assert node_count >= 3
    assert edge_count >= node_count - 1


@pytest.mark.parametrize("key", SCENARIO_KEYS)
def test_seed_scenario_has_baseline_candidate(db_session, key):
    incident_id = db_session.execute(
        text("SELECT incident_id FROM seed_scenarios WHERE scenario_key = :k"), {"k": key}
    ).scalar_one()
    baseline_count = db_session.execute(
        text(
            "SELECT count(*) FROM response_candidates "
            "WHERE incident_id = :iid AND candidate_type = 'baseline'"
        ),
        {"iid": incident_id},
    ).scalar_one()
    assert baseline_count >= 1


def test_unknown_scenario_key_returns_none(db_session):
    repo = SeedScenarioRepository(db_session)
    assert repo.by_key("존재하지않는시나리오") is None


def test_all_three_scenarios_are_distinct_incidents(db_session):
    repo = SeedScenarioRepository(db_session)
    scenarios = repo.all()
    keys = {s.scenario_key for s in scenarios}
    assert keys == set(SCENARIO_KEYS)
    incident_ids = {s.incident_id for s in scenarios}
    assert len(incident_ids) == 3
