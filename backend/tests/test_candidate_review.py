"""Tests for the 다중 관점 교차검증 (multi-perspective cross-review) service
(agents/response-optimization.md, simulation-supply-chain-tool.md §7.1 "Level
2") -- app/services/candidate_review.py.

Covers the required minimum 5 cases:
  1. Normal review generation: all 3 lenses populated per candidate, and the
     3 lenses were actually invoked with 3 DIFFERENT prompts (not the same
     prompt reused for all 3).
  2. Re-review is append-only: a second review run appends new rows; the
     first run's rows are untouched and still queryable with their original
     values.
  3. An LLM response that violates the shared LensReviewResult schema (e.g.
     missing concern_level) is retried once and then raises
     CandidateReviewError.
  4. Multiple candidates are reviewed independently -- each review row is
     correctly matched back to its own candidate_id under the nested
     asyncio.gather-based parallel dispatch (candidates in parallel, lenses
     within each candidate in parallel).
  5. A candidate with no simulation result at all is excluded from review
     (never sent to the LLM).

No real GEMINI_API_KEY / network call is ever exercised -- a scripted fake
LLMProvider is used throughout, matching the pattern in test_simulation.py.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.candidate_reviews import LENSES, CandidateReviewRepository
from app.repositories.response_candidates import ResponseCandidateRepository
from app.repositories.simulation_results import SimulationResultRepository
from app.services.candidate_review import (
    CandidateReviewError,
    review_candidate,
    review_candidates_for_incident,
)
from app.services.constraint_validation import validate_candidates
from app.services.operational_graph import IncidentNotFoundError
from app.services.response_design import generate_candidates
from app.services.simulation import simulate_candidates

client = TestClient(app)
_RUN_ID = uuid.uuid4().hex[:8]


@pytest.fixture(autouse=True)
def _fake_embeddings(monkeypatch):
    monkeypatch.setattr("app.rag.search.embed_text", lambda _text: [0.0] * 768)


class ScriptedCandidateProvider:
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


def _sim_json(expected_loss: float = 1_000_000) -> str:
    return json.dumps(
        {
            "expected_loss": expected_loss,
            "p90": expected_loss * 2,
            "cvar": expected_loss * 2.5,
            "confidence": 0.7,
            "sensitivity_variables": ["안전재고 소진 속도"],
            "fact": {"qty": 480},
            "inference": {"depletion_hours": 14},
            "assumption": {"consumption_rate": "steady"},
        }
    )


class ScriptedSimProvider:
    def __init__(self, expected_loss: float = 1_000_000):
        self._expected_loss = expected_loss

    def generate(self, prompt: str, *, system=None, temperature: float = 0.7) -> str:
        return _sim_json(self._expected_loss)


_LENS_MARKERS = {
    "cost": "비용(cost) 관점",
    "feasibility": "실행가능성(feasibility) 관점",
    "risk": "리스크(risk) 관점",
}


def _lens_of(prompt: str) -> str:
    for lens, marker in _LENS_MARKERS.items():
        if marker in prompt:
            return lens
    raise AssertionError(f"prompt matched no known lens marker: {prompt[:200]!r}")


class ScriptedReviewProvider:
    """Fake LLMProvider for the review stage. Distinguishes which lens is
    being asked by matching a marker string each lens's prompt (and only
    that lens's prompt) contains -- see app/services/candidate_review.py's
    3 separate `_build_*_lens_prompt` functions."""

    def __init__(self, concern_by_lens: dict[str, str] | None = None):
        self._concern_by_lens = concern_by_lens or {}
        self.prompts: list[str] = []
        self.call_count = 0

    def generate(self, prompt: str, *, system=None, temperature: float = 0.7) -> str:
        self.prompts.append(prompt)
        self.call_count += 1
        lens = _lens_of(prompt)
        concern = self._concern_by_lens.get(lens, "low")
        return json.dumps(
            {
                "concern_level": concern,
                "comment": f"{lens} 관점에서 검토한 결과입니다.",
                "flags": [f"{lens}-flag"] if concern != "low" else [],
            }
        )


class BadThenBadProvider:
    """Always returns a schema-violating response (missing concern_level)
    for every lens -- used to exercise the retry-once-then-raise contract."""

    def __init__(self):
        self.call_count = 0

    def generate(self, prompt: str, *, system=None, temperature: float = 0.7) -> str:
        self.call_count += 1
        return json.dumps({"comment": "concern_level이 빠진 응답", "flags": []})


def _loc(base: str) -> str:
    return f"{base} ({_RUN_ID})"


def _create_incident(type_: str, location: str) -> dict:
    unique_container = f"CTN-REV-{uuid.uuid4().hex[:8]}"
    occurred_at = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "type": type_,
        "location": _loc(location),
        "occurred_at": occurred_at.isoformat(),
        "affected_targets": {
            "containers": [unique_container],
            "parts": ["PT-REV-1"],
            "production_orders": ["PO-REV-1"],
            "customers": ["Dealer-REV-1"],
        },
    }
    resp = client.post("/incidents", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _setup_simulated_incident(db_session, type_: str, location: str, expected_loss: float = 1_000_000) -> dict:
    """Creates an incident, runs stages 1-3 (design -> validate -> simulate)
    with scripted fakes, so at least one candidate has a simulation result
    and is therefore review-eligible."""
    incident = _create_incident(type_, location)
    asyncio.run(
        generate_candidates(db_session, incident["id"], llm_provider=ScriptedCandidateProvider())
    )
    validate_candidates(db_session, incident["id"])
    asyncio.run(
        simulate_candidates(db_session, incident["id"], llm_provider=ScriptedSimProvider(expected_loss))
    )
    return incident


# ------------------------------------------------------------------
# 1. Normal review generation -- 3 lenses, 3 different prompts
# ------------------------------------------------------------------


def test_review_candidates_produces_three_lenses_with_distinct_prompts(db_session):
    incident = _setup_simulated_incident(db_session, "항만 적체", "정상리뷰생성")

    sim_repo = SimulationResultRepository(db_session)
    candidate_repo = ResponseCandidateRepository(db_session)
    eligible = [c for c in candidate_repo.for_incident(incident["id"]) if sim_repo.latest_for_candidate(c.id)]
    assert eligible

    provider = ScriptedReviewProvider()
    reviews = asyncio.run(review_candidates_for_incident(db_session, incident["id"], llm_provider=provider))

    # 3 rows per eligible candidate.
    assert len(reviews) == 3 * len(eligible)

    review_repo = CandidateReviewRepository(db_session)
    for candidate in eligible:
        by_lens = review_repo.latest_by_lens_for_candidate(candidate.id)
        assert set(by_lens.keys()) == set(LENSES)
        for lens, review in by_lens.items():
            assert review.concern_level in ("low", "medium", "high")
            assert review.comment.strip()
            assert isinstance(review.flags, list)

    # The 3 lens prompts for the same candidate must be genuinely different
    # texts -- proof this is 3 independent calls, not one prompt reused.
    prompts_per_candidate = len(provider.prompts) // len(eligible)
    assert prompts_per_candidate == 3
    for i in range(len(eligible)):
        chunk = provider.prompts[i * 3 : i * 3 + 3]
        assert len(set(chunk)) == 3  # all 3 pairwise distinct


# ------------------------------------------------------------------
# 2. Re-review is append-only
# ------------------------------------------------------------------


def test_rereview_appends_new_rows_and_does_not_touch_old_ones(db_session):
    incident = _setup_simulated_incident(db_session, "항만 적체", "재검토append")

    candidate_repo = ResponseCandidateRepository(db_session)
    sim_repo = SimulationResultRepository(db_session)
    baseline = next(c for c in candidate_repo.for_incident(incident["id"]) if c.candidate_type == "baseline")
    sim = sim_repo.latest_for_candidate(baseline.id)
    assert sim is not None

    first_reviews = asyncio.run(
        review_candidate(db_session, baseline, sim, llm_provider=ScriptedReviewProvider({"cost": "high"}))
    )
    second_reviews = asyncio.run(
        review_candidate(db_session, baseline, sim, llm_provider=ScriptedReviewProvider({"cost": "low"}))
    )

    review_repo = CandidateReviewRepository(db_session)
    all_rows = review_repo.for_candidate(baseline.id)
    assert len(all_rows) == len(first_reviews) + len(second_reviews) == 6

    first_ids = {r.id for r in first_reviews}
    second_ids = {r.id for r in second_reviews}
    assert first_ids.isdisjoint(second_ids)  # distinct rows, nothing overwritten

    # The old cost-lens row is untouched: still 'high', not mutated to 'low'.
    old_cost_review = next(r for r in first_reviews if r.lens == "cost")
    reloaded = review_repo.get(old_cost_review.id)
    assert reloaded is not None
    assert reloaded.concern_level == "high"

    # latest_by_lens_for_candidate now points at the *second* run's rows.
    latest = review_repo.latest_by_lens_for_candidate(baseline.id)
    assert latest["cost"].id in second_ids
    assert latest["cost"].concern_level == "low"


# ------------------------------------------------------------------
# 3. Schema violation -> retry once, then raise
# ------------------------------------------------------------------


def test_schema_violation_missing_concern_level_retries_then_raises(db_session):
    incident = _setup_simulated_incident(db_session, "항만 적체", "리뷰스키마위반")

    provider = BadThenBadProvider()
    with pytest.raises(CandidateReviewError):
        asyncio.run(review_candidates_for_incident(db_session, incident["id"], llm_provider=provider))

    # Retried at least once per lens call before giving up.
    assert provider.call_count >= 2

    # No review row was persisted for the failed candidate's lens set.
    review_repo = CandidateReviewRepository(db_session)
    assert review_repo.for_incident(incident["id"]) == []


# ------------------------------------------------------------------
# 4. Multiple candidates reviewed independently / in parallel
# ------------------------------------------------------------------


def test_multiple_candidates_are_reviewed_independently(db_session):
    incident = _create_incident("항만 적체", "병렬리뷰")

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
    asyncio.run(simulate_candidates(db_session, incident["id"], llm_provider=ScriptedSimProvider(500_000)))

    candidate_repo = ResponseCandidateRepository(db_session)
    sim_repo = SimulationResultRepository(db_session)
    eligible = [c for c in candidate_repo.for_incident(incident["id"]) if sim_repo.latest_for_candidate(c.id)]
    assert len(eligible) >= 3  # baseline + the 2 above

    provider = ScriptedReviewProvider()
    reviews = asyncio.run(review_candidates_for_incident(db_session, incident["id"], llm_provider=provider))

    assert len(reviews) == 3 * len(eligible)
    reviewed_candidate_ids = {r.candidate_id for r in reviews}
    assert reviewed_candidate_ids == {c.id for c in eligible}

    review_repo = CandidateReviewRepository(db_session)
    for c in eligible:
        rows = review_repo.for_candidate(c.id)
        assert len(rows) == 3
        assert {r.lens for r in rows} == set(LENSES)
        assert all(r.candidate_id == c.id for r in rows)


# ------------------------------------------------------------------
# 5. Candidate with no simulation result is excluded from review
# ------------------------------------------------------------------


def test_candidate_without_simulation_result_is_excluded(db_session):
    incident = _create_incident("항만 적체", "미시뮬레이션제외")

    asyncio.run(
        generate_candidates(db_session, incident["id"], llm_provider=ScriptedCandidateProvider())
    )
    validate_candidates(db_session, incident["id"])
    # Deliberately skip simulate_candidates -- nothing has a simulation
    # result yet.

    provider = ScriptedReviewProvider()
    reviews = asyncio.run(review_candidates_for_incident(db_session, incident["id"], llm_provider=provider))

    assert reviews == []
    assert provider.call_count == 0  # never even called the LLM

    review_repo = CandidateReviewRepository(db_session)
    assert review_repo.for_incident(incident["id"]) == []


def test_review_candidates_for_incident_raises_not_found_for_unknown_incident(db_session):
    with pytest.raises(IncidentNotFoundError):
        asyncio.run(
            review_candidates_for_incident(db_session, 999999999, llm_provider=ScriptedReviewProvider())
        )


def test_review_candidates_returns_empty_list_when_nothing_eligible(db_session):
    incident = _create_incident("항만 적체", "리뷰대상없음")
    # No generate/validate/simulate calls at all yet.
    reviews = asyncio.run(
        review_candidates_for_incident(db_session, incident["id"], llm_provider=ScriptedReviewProvider())
    )
    assert reviews == []
