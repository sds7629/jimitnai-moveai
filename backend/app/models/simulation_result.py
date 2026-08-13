from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Numeric, String, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SimulationResult(Base):
    """Append-only — same baseline-immutability rationale as
    OperationalSnapshot. Re-simulation always inserts a new row."""

    __tablename__ = "simulation_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("response_candidates.id"), nullable=False
    )
    incident_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("incidents.id"), nullable=False)
    expected_loss: Mapped[Decimal | None] = mapped_column(Numeric)
    p90: Mapped[Decimal | None] = mapped_column(Numeric)
    cvar: Mapped[Decimal | None] = mapped_column(Numeric)
    sensitivity_variables: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric)
    fact: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    inference: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    assumption: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    data_version: Mapped[str] = mapped_column(String, nullable=False)
    scenario_version: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
