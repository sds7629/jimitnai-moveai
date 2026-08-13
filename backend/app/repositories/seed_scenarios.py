from __future__ import annotations

from app.models.seed_scenario import SeedScenario
from app.repositories.base import AppendOnlyRepository


class SeedScenarioRepository(AppendOnlyRepository[SeedScenario]):
    model = SeedScenario

    def by_key(self, scenario_key: str) -> SeedScenario | None:
        return (
            self.db.query(SeedScenario)
            .filter(SeedScenario.scenario_key == scenario_key)
            .one_or_none()
        )

    def all(self) -> list[SeedScenario]:
        return self.db.query(SeedScenario).order_by(SeedScenario.id.asc()).all()
