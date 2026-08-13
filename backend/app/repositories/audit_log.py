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

    def sop_dispatched_events_for_incident(self, incident_id: int) -> list[AuditLog]:
        """All `event_type='sop_dispatched'` rows for an incident, oldest
        first. communication-sop wave convention (app/services/
        communication.py): there is no dedicated SOP table -- each such row
        *is* one role's SOP dispatch, and that row's own `id` is the
        `sop_id` referenced by every later status update for it (see
        `sop_dispatches_for_approval` below and GET /incidents/{id}/sop-status)."""

        return (
            self.db.query(AuditLog)
            .filter(AuditLog.incident_id == incident_id)
            .filter(AuditLog.event_type == "sop_dispatched")
            .order_by(AuditLog.id.asc())
            .all()
        )

    def sop_dispatches_for_approval(self, incident_id: int, approval_id: int) -> list[AuditLog]:
        """The subset of `sop_dispatched` rows created for one specific
        approval -- used by dispatch_sop's idempotency check (a given
        approval_id must only ever produce one dispatch per role, even if
        the endpoint is called again)."""

        return (
            self.db.query(AuditLog)
            .filter(AuditLog.incident_id == incident_id)
            .filter(AuditLog.event_type == "sop_dispatched")
            .filter(AuditLog.payload["approval_id"].astext == str(approval_id))
            .order_by(AuditLog.id.asc())
            .all()
        )
