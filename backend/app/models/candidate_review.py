from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CandidateReview(Base):
    """Append-only -- 다중 관점 교차검증(cost/feasibility/risk) 결과.

    Same baseline-immutability rationale as SimulationResult: a candidate's
    review history must stay fully auditable, so re-review (e.g. after a
    fresh simulation_results row) always inserts new rows per lens rather
    than mutating a prior lens's verdict. There is no update()/delete() on
    CandidateReviewRepository (app/repositories/base.py's AppendOnlyRepository),
    and the `moveai_app` DB role has no UPDATE/DELETE grant on this table
    (db/init/004-permissions.sql)."""

    __tablename__ = "candidate_reviews"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("response_candidates.id"), nullable=False
    )
    incident_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("incidents.id"), nullable=False)
    simulation_result_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("simulation_results.id")
    )
    lens: Mapped[str] = mapped_column(String, nullable=False)
    concern_level: Mapped[str] = mapped_column(String, nullable=False)
    comment: Mapped[str] = mapped_column(String, nullable=False)
    flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
