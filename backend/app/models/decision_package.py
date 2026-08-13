from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DecisionPackage(Base):
    """`package` (JSONB) is expected to carry the 10 items from
    simulation-supply-chain-tool.md §5.1 — expected loss/P90/CVaR, now vs
    +6h vs no-action comparison, causal path, data/documents used,
    FACT/INFERENCE/ASSUMPTION tagging, freshness/coverage, key sensitivity
    variables, feasibility/exclusion reasons, confidence/uncertainty range.
    Treated as append-only in the repository layer: recomputation inserts
    a new package row rather than mutating the previous one."""

    __tablename__ = "decision_packages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    incident_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("incidents.id"), nullable=False)
    package: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    recommended_deadline: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
