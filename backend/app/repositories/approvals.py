from __future__ import annotations

from app.models.approval import Approval
from app.repositories.base import AppendOnlyRepository


class ApprovalRepository(AppendOnlyRepository[Approval]):
    model = Approval

    def for_incident(self, incident_id: int) -> list[Approval]:
        return (
            self.db.query(Approval)
            .filter(Approval.incident_id == incident_id)
            .order_by(Approval.decided_at.asc())
            .all()
        )
