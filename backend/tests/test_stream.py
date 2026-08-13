"""Tests for GET /incidents/{id}/stream (agents/orchestration.md) --
app/api/stream.py.

The real endpoint's generator loops forever (`max_iterations=None`) for as
long as the client stays connected -- an infinite-loop test would hang, so:
  1. The generator function `event_stream` is exercised directly with a
     small `max_iterations`, bypassing HTTP entirely (fast, deterministic).
  2. One HTTP-level smoke test confirms the endpoint actually wires
     `event_stream` into a real `StreamingResponse` with the right media
     type, by monkeypatching the module-level `event_stream` name the
     endpoint looks up at call time to a bounded variant + a near-zero poll
     interval, so the request completes on its own almost immediately
     instead of needing an external timeout/cancel.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.api.stream as stream_module
from app.main import app
from app.repositories.decision_packages import DecisionPackageRepository

client = TestClient(app)
_RUN_ID = uuid.uuid4().hex[:8]


class _FakeCandidateProvider:
    def generate(self, prompt, *, system=None, temperature=0.7):
        return json.dumps(
            {
                "candidates": [
                    {
                        "response_category": "긴급운송",
                        "candidate_type": "단일",
                        "description": "긴급 대체 운송 수배",
                        "preconditions": [],
                        "start_time_variant": "now",
                        "reference_document_ids": [],
                    }
                ]
            }
        )


class _FakeSimProvider:
    def generate(self, prompt, *, system=None, temperature=0.7):
        return json.dumps(
            {
                "expected_loss": 900_000,
                "p90": 1_800_000,
                "cvar": 2_100_000,
                "confidence": 0.6,
                "sensitivity_variables": ["운송 리드타임"],
                "fact": {"qty": 300},
                "inference": {"depletion_hours": 8},
                "assumption": {"consumption_rate": "steady"},
            }
        )


@pytest.fixture(autouse=True)
def _fake_llm_and_embeddings(monkeypatch):
    monkeypatch.setattr("app.rag.search.embed_text", lambda _text: [0.0] * 768)
    monkeypatch.setattr("app.services.response_design.get_llm_provider", lambda: _FakeCandidateProvider())
    monkeypatch.setattr("app.services.simulation.get_llm_provider", lambda: _FakeSimProvider())


def _loc(base: str) -> str:
    return f"{base} ({_RUN_ID}-{uuid.uuid4().hex[:6]})"


def _create_incident_with_package(type_: str, location: str) -> int:
    unique_container = f"CTN-SSE-{uuid.uuid4().hex[:8]}"
    occurred_at = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "type": type_,
        "location": _loc(location),
        "occurred_at": occurred_at.isoformat(),
        "affected_targets": {
            "containers": [unique_container],
            "parts": ["PT-SSE-1"],
            "production_orders": ["PO-SSE-1"],
            "customers": ["Dealer-SSE-1"],
        },
    }
    resp = client.post("/incidents", json=payload)
    assert resp.status_code == 201, resp.text
    incident_id = resp.json()["id"]

    sim_resp = client.post(f"/incidents/{incident_id}/simulate")
    assert sim_resp.status_code == 200, sim_resp.text

    package_resp = client.get(f"/incidents/{incident_id}/decision-package")
    assert package_resp.status_code == 200, package_resp.text

    return incident_id


def _parse_sse_events(blocks: list[str]) -> list[dict]:
    """Each element of `blocks` is one full SSE block as produced by
    app/api/stream.py's `_sse_line` -- "event: <type>\ndata: <json>\n\n" all
    in one string, not pre-split into individual lines -- so this must split
    each block itself before looking for its `data:` line."""
    events = []
    for block in blocks:
        for line in block.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


# ------------------------------------------------------------------
# 1. Generator-level: first tick emits at least a decision_package_updated
#    event for an incident that already has a package + snapshot.
# ------------------------------------------------------------------


def test_event_stream_emits_at_least_one_event_on_first_tick(monkeypatch):
    monkeypatch.setattr(stream_module, "POLL_INTERVAL_SECONDS", 0.01)
    incident_id = _create_incident_with_package("항만 적체", "SSE첫틱")

    async def _collect():
        lines = []
        async for line in stream_module.event_stream(incident_id, max_iterations=1):
            lines.append(line)
        return lines

    lines = asyncio.run(_collect())
    events = _parse_sse_events(lines)

    assert events, "expected at least one SSE event on the first poll tick"
    event_types = {e["type"] for e in events}
    assert "decision_package_updated" in event_types
    assert "dag_updated" in event_types
    for e in events:
        assert e["incident_id"] == incident_id


# ------------------------------------------------------------------
# 2. No duplicate events across ticks when nothing changed in between.
# ------------------------------------------------------------------


def test_event_stream_does_not_repeat_unchanged_events(monkeypatch):
    monkeypatch.setattr(stream_module, "POLL_INTERVAL_SECONDS", 0.01)
    incident_id = _create_incident_with_package("항만 파업", "SSE중복없음")

    async def _collect(n: int):
        lines = []
        async for line in stream_module.event_stream(incident_id, max_iterations=n):
            lines.append(line)
        return lines

    first_pass = asyncio.run(_collect(1))
    second_pass_lines = []

    async def _collect_two_ticks():
        result = []
        async for line in stream_module.event_stream(incident_id, max_iterations=2):
            result.append(line)
        return result

    # A fresh generator (fresh _StreamState) sees the same package/snapshot as
    # "new" once on tick 1, then must emit nothing new on tick 2 since nothing
    # changed in between.
    two_tick_lines = asyncio.run(_collect_two_ticks())
    tick_one_events = _parse_sse_events(first_pass)
    two_tick_events = _parse_sse_events(two_tick_lines)

    assert len(two_tick_events) == len(tick_one_events)


# ------------------------------------------------------------------
# 3. A brand-new decision package (re-simulation) after the stream has
#    already seen one produces a fresh decision_package_updated event on a
#    later tick.
# ------------------------------------------------------------------


def test_event_stream_emits_new_event_when_package_changes(monkeypatch):
    monkeypatch.setattr(stream_module, "POLL_INTERVAL_SECONDS", 0.01)
    incident_id = _create_incident_with_package("관세 규정 변경", "SSE갱신")

    state = stream_module._StreamState()
    first_tick_lines = stream_module._poll_once(incident_id, state)
    assert _parse_sse_events(first_tick_lines)  # first tick always reports what already exists

    second_tick_lines = stream_module._poll_once(incident_id, state)
    assert second_tick_lines == []  # nothing changed yet

    # Force a brand-new decision_packages row (simulating a re-simulation),
    # append-only per app/repositories/decision_packages.py.
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings
    from sqlalchemy import create_engine

    engine = create_engine(settings.database_url, future=True)
    Session = sessionmaker(bind=engine, future=True)
    db = Session()
    try:
        DecisionPackageRepository(db).add(incident_id=incident_id, package={"disclaimer": "re-simulated"})
    finally:
        db.close()

    third_tick_lines = stream_module._poll_once(incident_id, state)
    third_tick_events = _parse_sse_events(third_tick_lines)
    assert any(e["type"] == "decision_package_updated" for e in third_tick_events)


# ------------------------------------------------------------------
# 4. HTTP-level smoke test: real endpoint, real StreamingResponse, bounded
#    so the request completes on its own instead of hanging.
# ------------------------------------------------------------------


def test_stream_endpoint_returns_event_stream_over_http(monkeypatch):
    monkeypatch.setattr(stream_module, "POLL_INTERVAL_SECONDS", 0.01)
    incident_id = _create_incident_with_package("항만 적체", "SSE엔드포인트")

    original_event_stream = stream_module.event_stream

    def _bounded(incident_id_arg, max_iterations=None):
        return original_event_stream(incident_id_arg, max_iterations=2)

    monkeypatch.setattr(stream_module, "event_stream", _bounded)

    with client.stream("GET", f"/incidents/{incident_id}/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        lines = list(resp.iter_lines())

    events = _parse_sse_events(lines)
    assert events
    assert any(e["type"] == "decision_package_updated" for e in events)
