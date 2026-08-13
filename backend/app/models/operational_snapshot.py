from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, String, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OperationalSnapshot(Base):
    """Append-only — baseline immutability requirement (ARCHITECTURE.md §2,
    simulation-supply-chain-tool.md §3.3/§9). New state is always a new row;
    never UPDATE an existing snapshot."""

    __tablename__ = "operational_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    incident_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("incidents.id"), nullable=False)
    data_version: Mapped[str] = mapped_column(String, nullable=False)
    scenario_version: Mapped[str] = mapped_column(String, nullable=False)
    assumptions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    operational_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    quality_mode: Mapped[str] = mapped_column(String, nullable=False, default="normal")
    freshness_seconds: Mapped[int | None] = mapped_column(Integer)
    coverage_ratio: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
