from __future__ import annotations

from app.models.audit_log import AuditLog
from app.repositories.base import AppendOnlyRepository


class AuditLogRepository(AppendOnlyRepository[AuditLog]):
    model = AuditLog

    def timeline_for_incident(self, incident_id: int) -> list[AuditLog]:
        return (
            self.db.query(AuditLog)
            .filter(AuditLog.incident_id == incident_id)
            .order_by(AuditLog.created_at.asc())
            .all()
        )
