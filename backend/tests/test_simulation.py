"""Tests for the simulation agent (agents/simulation.md).

Covers the DoD's minimum 3 cases plus edge cases:
  1. Normal simulation result: FACT/INFERENCE/ASSUMPTION all filled, plus
     expected_loss/p90/cvar/confidence/sensitivity_variables.
  2. Re-simulation appends a new simulation_results row rather than
     touching the old one (append-only -- there is no update() method to
     even attempt to call, per app/repositories/simulation_results.py).
  3. An LLM response that violates the required schema (missing/empty
     `fact`) is retried once and then raises a clear error rather than
     silently accepting a numbers-only response.

Plus: 불가능 candidates are never sent to the LLM at all, and multiple
eligible candidates are each simulated independently and correctly matched
back to their own candidate_id under the asyncio.gather-based parallel
dispatch.

No real GEMINI_API_KEY / network call is ever exercised.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.llm import GeminiAPIError
from app.main import app
from app.repositories.response_candidates import ResponseCandidateRepository
from app.repositories.simulation_results import SimulationResultRepository
from app.services.constraint_validation import validate_candidates
from app.services.operational_graph import IncidentNotFoundError
from app.services.response_design import generate_candidates
from app.services.simulation import SimulationValidationError, simulate_candidates

client = TestClient(app)
_RUN_ID = uuid.uuid4().hex[:8]


@pytest.fixture(autouse=True)
def _fake_embeddings(monkeypatch):
    monkeypatch.setattr("app.rag.search.embed_text", lambda _text: [0.0] * 768)


class ScriptedCandidateProvider:
    """Fixed response for the response-design stage's single LLM call."""

    def __init__(self, description: str = "컨테이너 우선반출 시도"):
        self._description = description

    def generate(self, prompt: str, *, system=None, temperature: float = 0.7) -> str:
        return json.dumps(
            {
                "candidates": [
                    {
                        "response_category": "컨테이너 우선반출",
                        "candidate_type": "단일",
                        "description": self._description,
                        "preconditions": [],
                        "start_time_variant": "now",
                        "reference_document_ids": [],
                    }
                ]
            }
        )


def _sim_json(expected_loss: float = 1_000_000, sensitivity=None) -> str:
    return json.dumps(
        {
            "expected_loss": expected_loss,
            "p90": expected_loss * 2,
            "cvar": expected_loss * 2.5,
            "confidence": 0.7,
            "sensitivity_variables": sensitivity or ["안전재고 소진 속도"],
            "fact": {"qty": 480},
            "inference": {"depletion_hours": 14},
            "assumption": {"consumption_rate": "steady"},
        }
    )


class ScriptedSimProvider:
    def __init__(self, responses):
        self._responses = responses if isinstance(responses, list) else [responses]
        self.call_count = 0
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, system=None, temperature: float = 0.7) -> str:
        self.prompts.append(prompt)
        idx = min(self.call_count, len(self._responses) - 1)
        self.call_count += 1
        return self._responses[idx]


def _loc(base: str) -> str:
    return f"{base} ({_RUN_ID})"


def _create_incident(type_: str, location: str) -> dict:
    # Each incident gets its own container id -- reusing the same id across
    # incidents would (correctly) trip constraint-validation's cross-incident
    # resource-overlap heuristic (see test_constraint_validation.py) and make
    # unrelated tests here interfere with each other.
    unique_container = f"CTN-SIM-{uuid.uuid4().hex[:8]}"
    occurred_at = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "type": type_,
        "location": _loc(location),
        "occurred_at": occurred_at.isoformat(),
        "affected_targets": {
            "containers": [unique_container],
            "parts": ["PT-SIM-1"],
            "production_orders": ["PO-SIM-1"],
            "customers": ["Dealer-SIM-1"],
        },
    }
    resp = client.post("/incidents", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _setup_validated_incident(db_session, type_: str, location: str) -> dict:
    """Creates an incident with baseline (가능) + one 조건부/가능 candidate,
    ready for simulate_candidates."""
    incident = _create_incident(type_, location)
    asyncio.run(
        generate_candidates(db_session, incident["id"], llm_provider=ScriptedCandidateProvider())
    )
    validate_candidates(db_session, incident["id"])
    return incident


# ------------------------------------------------------------------
# 1. Normal simulation result
# ------------------------------------------------------------------


def test_simulate_produces_fact_inference_assumption_and_metrics(db_session):
    incident = _setup_validated_incident(db_session, "항만 적체", "정상시뮬레이션")

    results = asyncio.run(
        simulate_candidates(db_session, incident["id"], llm_provider=ScriptedSimProvider(_sim_json()))
    )

    candidate_repo = ResponseCandidateRepository(db_session)
    eligible_count = len(
        [c for c in candidate_repo.for_incident(incident["id"]) if c.validation_status in ("가능", "조건부")]
    )
    assert len(results) == eligible_count
    assert eligible_count >= 2  # baseline + at least the one LLM candidate

    for r in results:
        assert r.fact
        assert r.inference
        assert r.assumption
        assert r.expected_loss is not None
        assert r.p90 is not None
        assert r.cvar is not None
        assert r.confidence is not None
        assert r.sensitivity_variables


# ------------------------------------------------------------------
# 2. Re-simulation appends, never updates
# ------------------------------------------------------------------


def test_resimulate_appends_new_row_instead_of_updating(db_session):
    incident = _setup_validated_incident(db_session, "항만 적체", "재시뮬레이션append")

    first_results = asyncio.run(
        simulate_candidates(db_session, incident["id"], llm_provider=ScriptedSimProvider(_sim_json(1_000_000)))
    )
    second_results = asyncio.run(
        simulate_candidates(db_session, incident["id"], llm_provider=ScriptedSimProvider(_sim_json(2_000_000)))
    )

    sim_repo = SimulationResultRepository(db_session)
    all_rows = sim_repo.for_incident(incident["id"])

    assert len(all_rows) == len(first_results) + len(second_results)
    first_ids = {r.id for r in first_results}
    second_ids = {r.id for r in second_results}
    assert first_ids.isdisjoint(second_ids)  # distinct rows, nothing overwritten

    # The old rows are exactly as they were (still queryable, same value).
    old_row = sim_repo.get(next(iter(first_ids)))
    assert old_row is not None
    assert float(old_row.expected_loss) == 1_000_000

    # latest_for_candidate must point at the newer row for a shared candidate_id.
    shared_candidate_id = first_results[0].candidate_id
    latest = sim_repo.latest_for_candidate(shared_candidate_id)
    assert latest.created_at >= old_row.created_at


# ------------------------------------------------------------------
# 3. Schema violation -> retry once, then raise
# ------------------------------------------------------------------


def test_schema_violation_missing_fact_retries_then_raises(db_session):
    incident = _setup_validated_incident(db_session, "항만 적체", "스키마위반")

    bad_json = json.dumps(
        {
            "expected_loss": 1000,
            "p90": 2000,
            "cvar": 2500,
            "confidence": 0.5,
            "sensitivity_variables": ["x"],
            "fact": {},  # empty -- violates "must not be empty"
            "inference": {"a": "b"},
            "assumption": {"c": "d"},
        }
    )
    provider = ScriptedSimProvider([bad_json, bad_json])

    with pytest.raises(SimulationValidationError):
        asyncio.run(simulate_candidates(db_session, incident["id"], llm_provider=provider))

    # Retried exactly once per candidate before giving up. There is exactly
    # one eligible candidate whose (single) failure is enough to fail the
    # whole asyncio.gather -- so call_count reflects 2 tries for that one
    # candidate (other concurrent candidates may also have been called once
    # before the gather aborted, so we assert the minimum guaranteed count).
    assert provider.call_count >= 2

    # No row was persisted for the failed candidate.
    sim_repo = SimulationResultRepository(db_session)
    assert sim_repo.for_incident(incident["id"]) == []


# ------------------------------------------------------------------
# Extra: provider-level failures (quota exhausted, network error, etc.)
# must surface as SimulationValidationError, not leak as a raw
# GeminiAPIError/500 -- found during pre-merge review when testing against
# a real (but quota-exhausted) GEMINI_API_KEY.
# ------------------------------------------------------------------


class RaisingSimProvider:
    """Fake LLMProvider whose generate() always raises, simulating a real
    provider-level failure (e.g. 429 RESOURCE_EXHAUSTED)."""

    def __init__(self, exc: Exception):
        self._exc = exc
        self.call_count = 0

    def generate(self, prompt: str, *, system=None, temperature: float = 0.7) -> str:
        self.call_count += 1
        raise self._exc


def test_provider_error_during_simulation_call_retries_then_raises(db_session):
    incident = _setup_validated_incident(db_session, "항만 적체", "시뮬레이션프로바이더실패")
    provider = RaisingSimProvider(GeminiAPIError("429 RESOURCE_EXHAUSTED"))

    with pytest.raises(SimulationValidationError):
        asyncio.run(simulate_candidates(db_session, incident["id"], llm_provider=provider))

    assert provider.call_count >= 2  # same retry-once-then-raise contract as parse failures

    sim_repo = SimulationResultRepository(db_session)
    assert sim_repo.for_incident(incident["id"]) == []


def test_provider_error_during_rag_embedding_is_wrapped_as_simulation_validation_error(
    db_session, monkeypatch
):
    incident = _setup_validated_incident(db_session, "항만 적체", "시뮬레이션임베딩실패")

    def _raise(_text):
        raise GeminiAPIError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr("app.rag.search.embed_text", _raise)
    provider = ScriptedSimProvider(["should never be reached"])

    with pytest.raises(SimulationValidationError):
        asyncio.run(simulate_candidates(db_session, incident["id"], llm_provider=provider))

    # The LLM was never even called -- the RAG/embedding failure happens first.
    assert provider.call_count == 0


def test_free_text_only_response_is_rejected(db_session):
    """A response with plausible numbers but no fact/inference/assumption
    breakdown at all (just prose) must be rejected just like a
    JSON-parse failure -- agents/simulation.md: '근거를 댈 수 없는 숫자는
    내보내지 않는다'."""
    incident = _setup_validated_incident(db_session, "항만 적체", "자유텍스트근거거부")

    prose_only = "기대손실은 약 100만원이고 P90은 200만원, CVaR은 250만원으로 추정됩니다."
    provider = ScriptedSimProvider([prose_only, prose_only])

    with pytest.raises(SimulationValidationError):
        asyncio.run(simulate_candidates(db_session, incident["id"], llm_provider=provider))


# ------------------------------------------------------------------
# 불가능 candidates are never simulated
# ------------------------------------------------------------------


def test_infeasible_candidates_are_never_sent_to_llm(db_session):
    incident = _setup_validated_incident(db_session, "항만 적체", "불가능스킵")

    candidate_repo = ResponseCandidateRepository(db_session)
    all_candidates = candidate_repo.for_incident(incident["id"])
    non_baseline = next(c for c in all_candidates if c.candidate_type != "baseline")
    candidate_repo.update(
        non_baseline.id,
        validation_status="불가능",
        exclusion_category="자원부족",
        exclusion_detail="test forced exclusion",
    )

    provider = ScriptedSimProvider(_sim_json())
    results = asyncio.run(simulate_candidates(db_session, incident["id"], llm_provider=provider))

    simulated_candidate_ids = {r.candidate_id for r in results}
    assert non_baseline.id not in simulated_candidate_ids
    # Only the baseline (still 가능) should have been simulated.
    assert provider.call_count == len(results)


# ------------------------------------------------------------------
# Parallel dispatch: each candidate's result matches its own candidate_id
# ------------------------------------------------------------------


def test_multiple_eligible_candidates_each_get_their_own_result(db_session):
    incident = _create_incident("항만 적체", "병렬처리")
    provider = ScriptedCandidateProvider("컨테이너 우선반출 시도")

    class TwoCandidateProvider:
        def generate(self, prompt, *, system=None, temperature=0.7):
            return json.dumps(
                {
                    "candidates": [
                        {
                            "response_category": "컨테이너 우선반출",
                            "candidate_type": "단일",
                            "description": "컨테이너 우선반출 A",
                            "preconditions": [],
                            "start_time_variant": "now",
                            "reference_document_ids": [],
                        },
                        {
                            "response_category": "고객출고우선순위",
                            "candidate_type": "단일",
                            "description": "고객 우선순위 조정",
                            "preconditions": [],
                            "start_time_variant": "+6h",
                            "reference_document_ids": [],
                        },
                    ]
                }
            )

    asyncio.run(generate_candidates(db_session, incident["id"], llm_provider=TwoCandidateProvider()))
    validate_candidates(db_session, incident["id"])

    candidate_repo = ResponseCandidateRepository(db_session)
    eligible = [c for c in candidate_repo.for_incident(incident["id"]) if c.validation_status in ("가능", "조건부")]
    assert len(eligible) >= 3  # baseline + the 2 above (both should pass -- no blocking keywords for #2)

    sim_provider = ScriptedSimProvider(_sim_json(500_000))
    results = asyncio.run(simulate_candidates(db_session, incident["id"], llm_provider=sim_provider))

    assert len(results) == len(eligible)
    assert {r.candidate_id for r in results} == {c.id for c in eligible}
    assert sim_provider.call_count == len(eligible)


# ------------------------------------------------------------------
# Not-found
# ------------------------------------------------------------------


def test_simulate_candidates_raises_not_found_for_unknown_incident(db_session):
    with pytest.raises(IncidentNotFoundError):
        asyncio.run(simulate_candidates(db_session, 999999999, llm_provider=ScriptedSimProvider(_sim_json())))


def test_simulate_candidates_returns_empty_list_when_nothing_eligible(db_session):
    incident = _create_incident("항만 적체", "대상없음")
    # No generate/validate calls -- no candidates exist at all yet.
    results = asyncio.run(
        simulate_candidates(db_session, incident["id"], llm_provider=ScriptedSimProvider(_sim_json()))
    )
    assert results == []
