from __future__ import annotations

from app.models.operational_snapshot import OperationalSnapshot
from app.repositories.base import AppendOnlyRepository


class OperationalSnapshotRepository(AppendOnlyRepository[OperationalSnapshot]):
    """append-only — see module docstring in repositories/base.py. A
    "changed" snapshot is always a newly inserted row; the latest one for
    an incident is found by created_at DESC, never by editing a prior row."""

    model = OperationalSnapshot

    def latest_for_incident(self, incident_id: int) -> OperationalSnapshot | None:
        return (
            self.db.query(OperationalSnapshot)
            .filter(OperationalSnapshot.incident_id == incident_id)
            .order_by(OperationalSnapshot.created_at.desc())
            .first()
        )

    def history_for_incident(self, incident_id: int) -> list[OperationalSnapshot]:
        return (
            self.db.query(OperationalSnapshot)
            .filter(OperationalSnapshot.incident_id == incident_id)
            .order_by(OperationalSnapshot.created_at.asc())
            .all()
        )
