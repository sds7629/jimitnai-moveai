from datetime import timedelta

from app.repositories.incidents import IncidentRepository


def test_list_by_status_filters_to_requested_status(db_session):
    repo = IncidentRepository(db_session)
    valid = repo.list_by_status("유효")
    assert len(valid) >= 3  # all 3 seed scenarios start as '유효'
    assert all(i.status == "유효" for i in valid)


def test_list_by_status_none_returns_all_incidents(db_session):
    repo = IncidentRepository(db_session)
    everything = repo.list_by_status(None)
    assert len(everything) >= 3


def test_find_open_duplicates_matches_within_window(db_session):
    repo = IncidentRepository(db_session)
    target = next(i for i in repo.list_by_status("유효") if i.type == "항만 적체")
    dups = repo.find_open_duplicates(target.type, target.location, target.occurred_at, timedelta(hours=1))
    assert target.id in {d.id for d in dups}


def test_find_open_duplicates_excludes_events_outside_window(db_session):
    repo = IncidentRepository(db_session)
    target = next(i for i in repo.list_by_status("유효") if i.type == "항만 적체")
    far_away = target.occurred_at - timedelta(days=10)
    dups = repo.find_open_duplicates(target.type, target.location, far_away, timedelta(hours=1))
    assert target.id not in {d.id for d in dups}
