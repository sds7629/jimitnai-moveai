"""Pydantic response schema for GET /incidents/{id}/decision-package
(agents/response-optimization.md).

`package` is intentionally typed as `dict[str, Any]` rather than expanded
into ~10 nested Pydantic models -- its 10-item shape (§5.1) is documented
and enforced entirely in app/services/response_optimization.py, which is
the single place that builds it. The frontend's "근거 패널"
(ARCHITECTURE.md §7.1) consumes it as JSON already shaped exactly the way
each section needs to render (FACT/INFERENCE/ASSUMPTION badges, confidence,
decision-deadline countdown, etc).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DecisionPackageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    package: dict[str, Any]
    recommended_deadline: datetime | None
    created_at: datetime
