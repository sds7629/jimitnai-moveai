"""SQLAlchemy models for all platform tables.

These models exist for querying/inserting from application code — the
tables themselves are created by db/init/*.sql (docker-entrypoint-initdb.d
convention), not by SQLAlchemy metadata.create_all(). Importing this
package registers every model on `Base.metadata`, which is convenient for
tests that want to introspect column names but must never be used to
actually create tables in a running environment (that would drift from
the SQL migrations, which are the single source of truth for schema).
"""

from app.models.incident import Incident
from app.models.audit_log import AuditLog
from app.models.operational_snapshot import OperationalSnapshot
from app.models.impact_dag import ImpactDagNode, ImpactDagEdge
from app.models.response_candidate import ResponseCandidate
from app.models.simulation_result import SimulationResult
from app.models.decision_package import DecisionPackage
from app.models.approval import Approval
from app.models.document import Document, DocumentChunk
from app.models.seed_scenario import SeedScenario

__all__ = [
    "Incident",
    "AuditLog",
    "OperationalSnapshot",
    "ImpactDagNode",
    "ImpactDagEdge",
    "ResponseCandidate",
    "SimulationResult",
    "DecisionPackage",
    "Approval",
    "Document",
    "DocumentChunk",
    "SeedScenario",
]
