import json
from pathlib import Path

import pytest
from sqlalchemy import text

from app.repositories.seed_scenarios import SeedScenarioRepository

SCENARIO_KEYS = ["적체", "파업", "관세"]

# db/init/003-seed-scenarios.sql lives two levels above backend/ (repo_root/db/init/...).
_SEED_SQL_PATH = Path(__file__).resolve().parents[2] / "db" / "init" / "003-seed-scenarios.sql"


def _extract_operational_state_json_blocks(sql_text: str) -> list[dict]:
    """Pulls out each scenario's `operational_state` JSON object (the jsonb
    literal assigned in the SELECT of the `snap` CTE) by balancing braces
    starting from the `{` that opens the object containing `"inventory":`.
    Used instead of querying the live DB because the seed SQL only runs via
    docker-entrypoint-initdb.d on first container startup -- editing this
    file doesn't retroactively update an already-initialized dev DB volume,
    so these are read straight from the source-of-truth file."""
    blocks: list[dict] = []
    search_start = 0
    while True:
        idx = sql_text.find('"inventory":', search_start)
        if idx == -1:
            break
        start = sql_text.rfind("{", 0, idx)
        depth = 0
        i = start
        while i < len(sql_text):
            if sql_text[i] == "{":
                depth += 1
            elif sql_text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        blocks.append(json.loads(sql_text[start : i + 1]))
        search_start = i + 1
    return blocks


@pytest.fixture(scope="module")
def seed_sql_operational_states() -> dict[str, dict]:
    """{scenario_key: operational_state dict}, parsed straight from
    db/init/003-seed-scenarios.sql, in the same order the scenarios appear
    in the file (적체, 파업, 관세 -- matches SCENARIO_KEYS).

    db/ lives outside the backend service's docker-compose mount
    (`./backend:/app` only) -- these tests are skipped rather than failing
    when run inside that container, since the file is simply unreachable
    there, not broken."""
    if not _SEED_SQL_PATH.exists():
        pytest.skip(f"{_SEED_SQL_PATH} not reachable in this environment (e.g. backend docker container)")
    sql_text = _SEED_SQL_PATH.read_text(encoding="utf-8")
    blocks = _extract_operational_state_json_blocks(sql_text)
    assert len(blocks) == len(SCENARIO_KEYS), (
        f"expected {len(SCENARIO_KEYS)} operational_state blocks in {_SEED_SQL_PATH}, found {len(blocks)}"
    )
    return dict(zip(SCENARIO_KEYS, blocks))


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


# ------------------------------------------------------------------
# Currency fields (bug fix): expected_loss/p90/cvar coming out of the
# simulation LLM call were absurdly small (e.g. 14,200원) because the seed
# snapshots had no price data at all, so the LLM had no grounded numbers to
# compute a loss from. Each scenario's operational_state now carries
# unit_value_krw (부품 단가) under inventory.<part> and finished_unit_value_krw
# (완성차 1대 시장가치) under production.<production_order_id>.
#
# These read db/init/003-seed-scenarios.sql directly (via the
# seed_sql_operational_states fixture above) rather than querying the live
# DB: docker-entrypoint-initdb.d only runs seed SQL once, on a container's
# first startup with an empty data volume, so editing this file does not
# retroactively update the currently-running dev DB's already-seeded rows
# (confirmed: `docker exec ... db-1 psql` SELECTs against the live
# operational_snapshots rows for incidents 1/2/3 still show the pre-fix
# shape, with no unit_value_krw/finished_unit_value_krw). Re-seeding the
# live DB requires resetting the db_data volume, which is explicitly out of
# scope for this change -- the orchestrator will do that separately when
# verifying the real Gemini call against the live stack.
# ------------------------------------------------------------------


@pytest.mark.parametrize("key", SCENARIO_KEYS)
def test_seed_scenario_inventory_has_positive_unit_value_krw(seed_sql_operational_states, key):
    inventory = seed_sql_operational_states[key]["inventory"]
    assert inventory, f"scenario {key} missing inventory"
    for part, info in inventory.items():
        assert "unit_value_krw" in info, f"{key}/{part} missing unit_value_krw"
        assert info["unit_value_krw"] > 0, f"{key}/{part} unit_value_krw must be > 0"


@pytest.mark.parametrize("key", SCENARIO_KEYS)
def test_seed_scenario_production_has_positive_finished_unit_value_krw(seed_sql_operational_states, key):
    production = seed_sql_operational_states[key]["production"]
    assert production, f"scenario {key} missing production"
    for po, info in production.items():
        assert "finished_unit_value_krw" in info, f"{key}/{po} missing finished_unit_value_krw"
        assert info["finished_unit_value_krw"] > 0, f"{key}/{po} finished_unit_value_krw must be > 0"


@pytest.mark.parametrize("key", SCENARIO_KEYS)
def test_seed_scenario_existing_operational_fields_untouched(seed_sql_operational_states, key):
    """Adding the new currency fields must not remove/rename any field the
    backend already reads (constraint_validation.py reads qty/safety_stock,
    simulation.py's DAG summary reasoning relies on capacity_per_hour, etc.)."""
    state = seed_sql_operational_states[key]
    for part, info in state["inventory"].items():
        for required in ("qty", "unit", "hourly_consumption", "safety_stock"):
            assert required in info, f"{key}/{part} lost pre-existing field {required}"
    for po, info in state["production"].items():
        for required in ("line", "status", "capacity_per_hour"):
            assert required in info, f"{key}/{po} lost pre-existing field {required}"


@pytest.mark.parametrize("key", SCENARIO_KEYS)
def test_seed_scenario_line_halt_loss_rate_is_at_least_hundred_million_krw_per_hour(
    seed_sql_operational_states, key
):
    """Sanity check on the scale of the new price data: capacity_per_hour *
    finished_unit_value_krw (the hourly loss rate if the line fully halts)
    should land in the "억원 단위 이상" range so that a multi-hour/day halt
    plausibly reaches the 억원~수백억원 total-loss scale the frontend design
    (DAG_SCREEN_DESIGN_BRIEF.md, e.g. "996.1억원") assumes -- not the
    4-5 orders of magnitude too small values (14,200원 loss) observed
    against the real LLM before this fix."""
    state = seed_sql_operational_states[key]
    for po, info in state["production"].items():
        hourly_loss_rate = info["capacity_per_hour"] * info["finished_unit_value_krw"]
        assert hourly_loss_rate >= 100_000_000, (
            f"{key}/{po} hourly halt loss rate {hourly_loss_rate}원 is too small to reach "
            "an 억원-scale total loss over a multi-hour halt"
        )


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
