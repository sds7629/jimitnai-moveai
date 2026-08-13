from __future__ import annotations

from app.models.response_candidate import ResponseCandidate
from app.repositories.base import MutableRepository


class ResponseCandidateRepository(MutableRepository[ResponseCandidate]):
    """Mutable: the constraint-validation stage updates validation_status /
    exclusion_category / exclusion_detail in place on the same row created
    by the response-design stage."""

    model = ResponseCandidate

    def for_incident(self, incident_id: int) -> list[ResponseCandidate]:
        return (
            self.db.query(ResponseCandidate)
            .filter(ResponseCandidate.incident_id == incident_id)
            .order_by(ResponseCandidate.created_at.asc())
            .all()
        )

    def baseline_for_incident(self, incident_id: int) -> ResponseCandidate | None:
        return (
            self.db.query(ResponseCandidate)
            .filter(ResponseCandidate.incident_id == incident_id)
            .filter(ResponseCandidate.candidate_type == "baseline")
            .order_by(ResponseCandidate.created_at.desc())
            .first()
        )
