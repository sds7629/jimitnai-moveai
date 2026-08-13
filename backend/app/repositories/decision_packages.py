from __future__ import annotations

from app.models.decision_package import DecisionPackage
from app.repositories.base import AppendOnlyRepository


class DecisionPackageRepository(AppendOnlyRepository[DecisionPackage]):
    """Treated as append-only: a recomputed package (e.g. after
    re-simulation) is a new row, keeping the history of what was presented
    to the approver at each point in time (audit trail for approvals)."""

    model = DecisionPackage

    def latest_for_incident(self, incident_id: int) -> DecisionPackage | None:
        return (
            self.db.query(DecisionPackage)
            .filter(DecisionPackage.incident_id == incident_id)
            .order_by(DecisionPackage.created_at.desc())
            .first()
        )
