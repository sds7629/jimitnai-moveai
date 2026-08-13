from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SeedScenario(Base):
    __tablename__ = "seed_scenarios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String)
    seed_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    incident_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("incidents.id"))
    snapshot_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("operational_snapshots.id"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
