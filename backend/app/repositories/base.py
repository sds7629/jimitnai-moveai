"""Base repository classes.

`AppendOnlyRepository` deliberately does not define update()/delete()
methods — there is simply no method to call to mutate an existing row.
That is the primary enforcement mechanism requested by
agents/platform-infra.md (work item #2): other personas' service code
literally cannot compile a call to "update a snapshot" because the method
does not exist.

The secondary enforcement mechanism is at the database level: the
`moveai_app` role (which the backend connects as — see
app/core/config.py's database_url and db/init/004-permissions.sql) has no
UPDATE/DELETE grant on the append-only tables. So even a future developer
who bypasses the repository layer entirely and writes raw SQL against
these tables gets a permission-denied error from Postgres, not a silent
success.

`MutableRepository` extends the same base with an explicit update() for
tables where in-place field changes are the correct design (e.g.
response_candidates.validation_status, incidents.status).
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class AppendOnlyRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, db: Session):
        self.db = db

    def add(self, **fields: Any) -> ModelT:
        obj = self.model(**fields)
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def get(self, id_: int) -> ModelT | None:
        return self.db.get(self.model, id_)

    def list(self, **filters: Any) -> list[ModelT]:
        query = self.db.query(self.model)
        for key, value in filters.items():
            query = query.filter(getattr(self.model, key) == value)
        return query.order_by(self.model.id.asc()).all()

    def list_for_incident(self, incident_id: int) -> list[ModelT]:
        return (
            self.db.query(self.model)
            .filter(self.model.incident_id == incident_id)
            .order_by(self.model.created_at.asc())
            .all()
        )

    # NOTE: no update()/delete() here on purpose. See module docstring.


class MutableRepository(AppendOnlyRepository[ModelT]):
    """For tables where in-place updates are legitimate application state
    (not subject to the append-only/baseline-immutability rule)."""

    def update(self, id_: int, **fields: Any) -> ModelT | None:
        obj = self.get(id_)
        if obj is None:
            return None
        for key, value in fields.items():
            setattr(obj, key, value)
        self.db.commit()
        self.db.refresh(obj)
        return obj
