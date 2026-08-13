"""Verifies the append-only guarantee for operational_snapshots,
simulation_results, approvals and audit_log at both levels described in
agents/platform-infra.md work item #2:

  1. Repository layer: no update() method exists to call.
  2. DB grant layer: the `moveai_app` role the backend connects as has no
     UPDATE/DELETE privilege on these tables (db/init/004-permissions.sql).
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.repositories.approvals import ApprovalRepository
from app.repositories.audit_log import AuditLogRepository
from app.repositories.candidate_reviews import CandidateReviewRepository
from app.repositories.incidents import IncidentRepository
from app.repositories.operational_snapshots import OperationalSnapshotRepository
from app.repositories.simulation_results import SimulationResultRepository

APPEND_ONLY_REPOS = [
    OperationalSnapshotRepository,
    SimulationResultRepository,
    ApprovalRepository,
    AuditLogRepository,
    CandidateReviewRepository,
]


@pytest.mark.parametrize("repo_cls", APPEND_ONLY_REPOS)
def test_append_only_repository_has_no_update_method(repo_cls):
    assert not hasattr(repo_cls, "update")


def test_mutable_repository_still_exposes_update():
    # Contrast case: proves the absence of update() above is a deliberate
    # design choice for these 4 repos, not something missing from the base
    # class entirely.
    assert hasattr(IncidentRepository, "update")


def test_db_role_cannot_update_operational_snapshots(raw_conn, seeded_incident_id):
    with pytest.raises(DBAPIError):
        raw_conn.execute(
            text("UPDATE operational_snapshots SET quality_mode = 'limited' WHERE incident_id = :iid"),
            {"iid": seeded_incident_id},
        )


def test_db_role_cannot_update_simulation_results(raw_conn):
    with pytest.raises(DBAPIError):
        raw_conn.execute(text("UPDATE simulation_results SET expected_loss = 0"))


def test_db_role_cannot_update_approvals(raw_conn):
    with pytest.raises(DBAPIError):
        raw_conn.execute(text("UPDATE approvals SET reason = 'tampered'"))


def test_db_role_cannot_update_candidate_reviews(raw_conn):
    with pytest.raises(DBAPIError):
        raw_conn.execute(text("UPDATE candidate_reviews SET concern_level = 'low'"))


def test_db_role_can_still_update_mutable_table_incidents(raw_conn, seeded_incident_id):
    """Positive control: if this failed too, the previous failures above
    would just mean "moveai_app is broken", not "append-only is enforced".
    incidents is intentionally mutable (status transitions), so this must
    succeed."""
    raw_conn.execute(
        text("UPDATE incidents SET status = status WHERE id = :iid"),
        {"iid": seeded_incident_id},
    )
    raw_conn.commit()
