from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ImpactDagNode(Base):
    __tablename__ = "impact_dag_nodes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("operational_snapshots.id"), nullable=False
    )
    node_key: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    affected_target: Mapped[str | None] = mapped_column(String)
    expected_time: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    basis: Mapped[str | None] = mapped_column(String)
    responsible_party: Mapped[str | None] = mapped_column(String)
    uncertainty: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class ImpactDagEdge(Base):
    __tablename__ = "impact_dag_edges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("operational_snapshots.id"), nullable=False
    )
    from_node_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("impact_dag_nodes.id"), nullable=False)
    to_node_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("impact_dag_nodes.id"), nullable=False)
    basis: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
