from __future__ import annotations

from app.models.simulation_result import SimulationResult
from app.repositories.base import AppendOnlyRepository


class SimulationResultRepository(AppendOnlyRepository[SimulationResult]):
    """append-only — re-simulation inserts a new row; the baseline
    candidate's very first result stays queryable forever for avoided-loss
    calculations (simulation-supply-chain-tool.md §9)."""

    model = SimulationResult

    def latest_for_candidate(self, candidate_id: int) -> SimulationResult | None:
        return (
            self.db.query(SimulationResult)
            .filter(SimulationResult.candidate_id == candidate_id)
            .order_by(SimulationResult.created_at.desc())
            .first()
        )

    def for_incident(self, incident_id: int) -> list[SimulationResult]:
        return (
            self.db.query(SimulationResult)
            .filter(SimulationResult.incident_id == incident_id)
            .order_by(SimulationResult.created_at.asc())
            .all()
        )
