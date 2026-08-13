"""GET /incidents/{id}/stream (agents/orchestration.md).

This is the one endpoint in this wave that must be `async def` +
`StreamingResponse` -- not because of an LLM call, but because the "blocking
I/O" here is a connection that stays open and pushes updates over time
(CLAUDE.md 비동기 처리 원칙: the criterion is "실제로 블로킹 I/O가 있는가", and a
held-open SSE connection is exactly that). Every other function this wave
adds (process_approval's 승인/조건부승인/반려 branches, check_deadline_overrun)
stays plain synchronous DB work -- see app/services/orchestration.py.

WebSocket is not used here because only server -> client push is needed
(ARCHITECTURE.md §7.2) -- the client never needs to send anything back over
this connection.

Each poll tick opens and closes its own short-lived Session rather than
holding one open for the whole connection's lifetime, so every tick
observes whatever other requests have actually committed in the meantime.

Event shape: every pushed line carries an explicit "type" field in its JSON
payload (decision_package_updated / dag_updated / deadline_overrun) as well
as the SSE `event:` field itself, per agents/orchestration.md work item #3
("이벤트 타입을 페이로드에 명시") -- the frontend can switch on either. SOP
status-change events belong to the not-yet-built communication-sop wave and
are deliberately not emitted here; that wave only needs to add its own
`EVENT_*` constant + one more `if` branch inside `_poll_once` below, the
loop/session/formatting plumbing around it does not need to change.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.db import SessionLocal
from app.repositories.decision_packages import DecisionPackageRepository
from app.repositories.operational_snapshots import OperationalSnapshotRepository
from app.services.orchestration import check_deadline_overrun

router = APIRouter(prefix="/incidents", tags=["orchestration-stream"])

# "2~3초 간격" per the task brief -- a plain module constant (not a env-tunable
# setting) since there's no requirement to change it per-deployment; tests
# monkeypatch this constant directly to shrink the loop instead of waiting
# out a real multi-second interval.
POLL_INTERVAL_SECONDS = 2.0

EVENT_DECISION_PACKAGE_UPDATED = "decision_package_updated"
EVENT_DAG_UPDATED = "dag_updated"
EVENT_DEADLINE_OVERRUN = "deadline_overrun"


def _sse_line(event_type: str, data: dict) -> str:
    body = {"type": event_type, **data}
    return f"event: {event_type}\ndata: {json.dumps(body, ensure_ascii=False, default=str)}\n\n"


class _StreamState:
    """Tracks the last-seen id of each watched resource across poll ticks --
    plain instance state scoped to one connection's generator, not shared
    across connections/incidents."""

    def __init__(self) -> None:
        self.last_decision_package_id: int | None = None
        self.last_snapshot_id: int | None = None


def _poll_once(incident_id: int, state: _StreamState) -> list[str]:
    """One poll tick's worth of SSE lines, computed against a fresh, short-
    lived Session. Kept as a plain sync function (no blocking I/O of its own
    beyond fast local Postgres reads) -- only the *loop* around this needs to
    be async, per CLAUDE.md's 비동기 처리 원칙."""

    lines: list[str] = []
    db = SessionLocal()
    try:
        latest_package = DecisionPackageRepository(db).latest_for_incident(incident_id)
        if latest_package is not None and latest_package.id != state.last_decision_package_id:
            state.last_decision_package_id = latest_package.id
            lines.append(
                _sse_line(
                    EVENT_DECISION_PACKAGE_UPDATED,
                    {"incident_id": incident_id, "decision_package_id": latest_package.id},
                )
            )

        latest_snapshot = OperationalSnapshotRepository(db).latest_for_incident(incident_id)
        if latest_snapshot is not None and latest_snapshot.id != state.last_snapshot_id:
            state.last_snapshot_id = latest_snapshot.id
            lines.append(
                _sse_line(
                    EVENT_DAG_UPDATED,
                    {"incident_id": incident_id, "snapshot_id": latest_snapshot.id},
                )
            )

        if check_deadline_overrun(db, incident_id):
            lines.append(_sse_line(EVENT_DEADLINE_OVERRUN, {"incident_id": incident_id}))
    finally:
        db.close()

    return lines


async def event_stream(incident_id: int, max_iterations: int | None = None) -> AsyncGenerator[str, None]:
    """The actual generator. `max_iterations` has no effect on the real
    endpoint (always None there -- an SSE connection runs until the client
    disconnects) but lets tests exercise a bounded number of poll ticks
    directly, without needing to race a real open HTTP connection against a
    timeout."""

    state = _StreamState()
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        iterations += 1
        for line in _poll_once(incident_id, state):
            yield line
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


@router.get("/{incident_id}/stream")
async def stream_incident_updates(incident_id: int) -> StreamingResponse:
    """No 404 for an unknown/not-yet-eligible incident_id -- an SSE stream is
    long-lived and the incident may not have a decision package or snapshot
    yet at connection time (e.g. opened right after the incident was
    reported, before /simulate has ever run); `_poll_once` simply emits
    nothing until something actually appears. This matches how the frontend
    is expected to use it (ARCHITECTURE.md §7.2): open the stream once per
    incident and just wait for events, rather than treating "nothing yet" as
    an error."""

    return StreamingResponse(event_stream(incident_id), media_type="text/event-stream")
