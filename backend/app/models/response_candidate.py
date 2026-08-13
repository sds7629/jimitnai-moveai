from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ResponseCandidate(Base):
    """Mutable — validation_status/exclusion_* are updated in place by the
    constraint-validation stage. Not subject to the append-only rule."""

    __tablename__ = "response_candidates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    incident_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("incidents.id"), nullable=False)
    snapshot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("operational_snapshots.id"), nullable=False
    )
    candidate_type: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    reference_document_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    preconditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    start_time_variant: Mapped[str | None] = mapped_column(String)
    validation_status: Mapped[str] = mapped_column(String, nullable=False, default="미검증")
    exclusion_category: Mapped[str | None] = mapped_column(String)
    exclusion_detail: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
