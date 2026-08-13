from __future__ import annotations

from app.models.impact_dag import ImpactDagEdge, ImpactDagNode
from app.repositories.base import AppendOnlyRepository


class ImpactDagNodeRepository(AppendOnlyRepository[ImpactDagNode]):
    """A DAG is tied to one immutable snapshot; re-deriving the DAG after a
    material change means creating a new snapshot + new nodes, never
    editing old ones. append-only for the same reason as
    OperationalSnapshot."""

    model = ImpactDagNode

    def for_snapshot(self, snapshot_id: int) -> list[ImpactDagNode]:
        return (
            self.db.query(ImpactDagNode)
            .filter(ImpactDagNode.snapshot_id == snapshot_id)
            .order_by(ImpactDagNode.id.asc())
            .all()
        )


class ImpactDagEdgeRepository(AppendOnlyRepository[ImpactDagEdge]):
    model = ImpactDagEdge

    def for_snapshot(self, snapshot_id: int) -> list[ImpactDagEdge]:
        return (
            self.db.query(ImpactDagEdge)
            .filter(ImpactDagEdge.snapshot_id == snapshot_id)
            .order_by(ImpactDagEdge.id.asc())
            .all()
        )
