from __future__ import annotations

from datetime import timedelta

from app.models.incident import Incident
from app.repositories.base import MutableRepository


class IncidentRepository(MutableRepository[Incident]):
    """incidents is NOT append-only (ARCHITECTURE.md §2 table lists it
    without that constraint) — status transitions (신규->중복/오탐/유효/...)
    are legitimate in-place updates here. The transition itself must still
    be recorded in audit_log by the caller (incident-intake persona)."""

    model = Incident

    def find_open_duplicates(self, type_: str, location: str, occurred_at, window: timedelta):
        """First-pass duplicate filter (incident-intake.md work item #2):
        same type + same location + occurred_at within `window`, and not
        already closed/dismissed."""
        lower = occurred_at - window
        upper = occurred_at + window
        return (
            self.db.query(Incident)
            .filter(Incident.type == type_)
            .filter(Incident.location == location)
            .filter(Incident.occurred_at.between(lower, upper))
            .filter(Incident.status.notin_(["오탐", "종료"]))
            .order_by(Incident.occurred_at.asc())
            .all()
        )

    def list_by_status(self, status: str | None = None) -> list[Incident]:
        query = self.db.query(Incident)
        if status is not None:
            query = query.filter(Incident.status == status)
        return query.order_by(Incident.created_at.desc()).all()
