"""다중 관점 교차검증 (agents/response-optimization.md, simulation-supply-
chain-tool.md §7.1 대응 최적화 에이전트 -- "Level 2" toward a real multi-agent
architecture).

So far every LLM-backed stage in this pipeline has been "one prompt -> one
result" (response-design: one call producing candidates; simulation: one
call per candidate producing a loss estimate). This module adds a 4th
pipeline stage: for every candidate that already has a simulation result,
run 3 INDEPENDENT LLM calls -- one per lens (cost/feasibility/risk) -- each
producing its own concern assessment, instead of asking one LLM call to
"answer from 3 perspectives".

Why 3 separate functions/prompts instead of one combined prompt with
if-branches: this mirrors app/rag/chunking.py's per-doc-type chunkers
(chunk_contract/chunk_sop/chunk_incident/chunk_playbook) -- a genuinely
different unit of analysis per case, kept as genuinely separate functions
rather than one function with a type switch. Here the reason is stronger
than "different structure": a single LLM call asked to produce all 3
verdicts at once is not independent cross-validation at all -- the model's
own cost opinion would bleed into what it writes for risk in the same
completion. Only 3 separate calls (parallelized via asyncio.gather, same
as simulation.py) are actually independent enough to be worth calling
"cross-review".

- **cost lens**: is the simulation's expected_loss/P90/CVaR internally
  consistent with the candidate's own description/preconditions, and are
  there cost items (LD/D&D exposure, extra resource costs) the simulation's
  fact/inference/assumption never mentions?
- **feasibility lens**: do the candidate's preconditions/validation_status
  plus the current operational snapshot suggest organizational/timing/
  coordination risk that constraint-validation's resource-capacity
  heuristics (app/services/constraint_validation.py) would not catch?
- **risk lens**: given sensitivity_variables/assumption/confidence, is the
  stated confidence overconfident relative to the number/nature of
  assumptions baked into the estimate, or is there hidden uncertainty?

Every lens's response is validated against the shared `LensReviewResult`
schema (concern_level/comment/flags) with the same retry-once-then-raise
contract as `simulation.py`'s `_generate_and_parse_with_retry`.

`candidate_reviews` is append-only (see
app/repositories/candidate_reviews.py -- no update() method exists); every
call inserts new rows and never touches a prior review, so re-reviewing a
candidate (e.g. after a fresh simulation) is a new "version", not a
correction of the old one.

Async / parallelism: `provider.generate()` is a synchronous, blocking call,
so every function here that calls it is `async def` and wraps the call in
`asyncio.to_thread` (CLAUDE.md 비동기 처리 원칙). Two levels of parallelism are
intentional: `review_candidate` fires all 3 lens calls for one candidate
concurrently via `asyncio.gather`, and `review_candidates_for_incident`
fires `review_candidate` for every eligible candidate concurrently via
`asyncio.gather` as well (nested parallelism). This is safe with a single
synchronous SQLAlchemy `Session` for the same reason it already is in
`simulate_candidates`: every DB read/write here is a plain synchronous
call that runs to completion without yielding control back to the event
loop, so nothing ever touches the Session concurrently -- only the network
round-trips (wrapped in `asyncio.to_thread`) actually run in parallel.

No text produced by this module (prompts, comments persisted from the LLM,
or the service's own docstrings) ever asserts that a candidate "is/is not
the correct response" -- lens reviews surface concerns for a human
reviewer, they are not a verdict (same principle as
app/services/response_optimization.py's DISCLAIMER).
"""

from __future__ import annotations

import asyncio
import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.llm import ClaudeCLIError, GeminiAPIError, LLMProvider, get_llm_provider
from app.llm.json_utils import extract_json
from app.models.candidate_review import CandidateReview
from app.models.operational_snapshot import OperationalSnapshot
from app.models.response_candidate import ResponseCandidate
from app.models.simulation_result import SimulationResult
from app.repositories.candidate_reviews import LENSES, CandidateReviewRepository
from app.repositories.incidents import IncidentRepository
from app.repositories.operational_snapshots import OperationalSnapshotRepository
from app.repositories.response_candidates import ResponseCandidateRepository
from app.repositories.simulation_results import SimulationResultRepository
from app.services.operational_graph import IncidentNotFoundError

__all__ = [
    "review_candidate",
    "review_candidates_for_incident",
    "CandidateReviewError",
    "LensReviewResult",
    "IncidentNotFoundError",
    "LENSES",
]

LENS_COST = "cost"
LENS_FEASIBILITY = "feasibility"
LENS_RISK = "risk"


class CandidateReviewError(RuntimeError):
    """A lens review's LLM response could not be parsed/validated against
    `LensReviewResult`, even after one retry (mirrors
    `SimulationValidationError` in app/services/simulation.py)."""


# ------------------------------------------------------------------
# Response schema shared by all 3 lenses -- concern_level/comment/flags
# enforced as top-level required fields, same "schema-level enforcement,
# not just a warning" approach as SimulationLLMResult in simulation.py.
# ------------------------------------------------------------------


class LensReviewResult(BaseModel):
    concern_level: Literal["low", "medium", "high"]
    comment: str
    flags: list[str] = Field(default_factory=list)

    @field_validator("comment")
    @classmethod
    def _comment_must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("comment 필드는 빈 문자열일 수 없습니다 (근거 없는 검토는 허용되지 않음)")
        return value


# ------------------------------------------------------------------
# Prompt construction -- 3 separate functions, one per lens. Deliberately
# NOT a single function branching on a `lens` argument: each lens looks at
# a different slice of the candidate/simulation/snapshot data and asks a
# different question, and keeping them textually separate is what makes it
# obvious at a glance that no single LLM call is doing double duty across
# perspectives.
# ------------------------------------------------------------------


def _build_cost_lens_prompt(candidate: ResponseCandidate, sim: SimulationResult) -> str:
    return f"""당신은 공급망 위기대응 도구의 "다중 관점 교차검증" 중 비용(cost) 관점 검토자다.
이 대응안 하나의 시뮬레이션 결과가 비용 측면에서 내적으로 일관되는지, 그리고 시뮬레이션이
놓쳤을 수 있는 비용 항목이 있는지만 검토하라. 다른 후보와 비교하거나 이 대응안의 최종 채택
여부를 판단하지 마라 -- 그건 이 역할의 책임이 아니고, 이 검토는 우려사항을 드러낼 뿐 정답을
단정하지 않는다.

## 대응안
유형: {candidate.candidate_type}
설명: {candidate.description}
선행조건: {candidate.preconditions}
검증상태: {candidate.validation_status}

## 시뮬레이션 결과
기대손실(expected_loss): {sim.expected_loss}
P90: {sim.p90}
CVaR: {sim.cvar}
신뢰도(confidence): {sim.confidence}
fact: {sim.fact}
inference: {sim.inference}
assumption: {sim.assumption}

## 지시사항
- 위 기대손실/P90/CVaR 숫자가 대응안의 설명·선행조건과 비교했을 때 비용 측면에서 서로 앞뒤가
  맞는지 검토하라 (예: 긴급 운송처럼 명백히 추가비용이 드는 대응인데 기대손실이 baseline과
  비슷하거나 더 낮다면 의심스러운 신호다).
- LD(Liquidated Damages)/D&D(Detention & Demurrage) 노출, 추가 인력/장비 등 실제로 들어갈 수
  있는데 위 시뮬레이션 근거(fact/inference/assumption)에 전혀 언급되지 않은 비용 항목이 있는지
  찾아 flags 배열에 문자열로 나열하라 (없으면 빈 배열).
- concern_level은 low/medium/high 중 하나로 답하라. 명확한 우려사항이 없으면 low, 숫자 불일치나
  누락된 비용 항목이 있으면 medium 이상으로 답하라.
- comment에는 반드시 판단 근거를 채워라. 근거 없는 빈 문장은 허용되지 않는다.
- 반드시 아래 JSON 스키마 하나만 응답하라. 다른 설명 텍스트나 마크다운 코드펜스를 붙이지 마라.

{{"concern_level": "low", "comment": "string", "flags": ["string"]}}
"""


def _build_feasibility_lens_prompt(
    candidate: ResponseCandidate, sim: SimulationResult, snapshot: OperationalSnapshot | None
) -> str:
    if snapshot is not None:
        snapshot_summary = (
            f"data_version={snapshot.data_version}, scenario_version={snapshot.scenario_version}, "
            f"quality_mode={snapshot.quality_mode}, freshness_seconds={snapshot.freshness_seconds}, "
            f"coverage_ratio={snapshot.coverage_ratio}\noperational_state: {snapshot.operational_state}"
        )
    else:
        snapshot_summary = "(운영 스냅샷을 찾을 수 없음)"

    return f"""당신은 공급망 위기대응 도구의 "다중 관점 교차검증" 중 실행가능성(feasibility) 관점
검토자다. 제약 검증 단계는 자원·비용·계약·운영시간 같은 정량적 자원 휴리스틱만 확인한다 -- 네
역할은 그 휴리스틱이 놓칠 수 있는 조직/시점/조율 리스크를 찾는 것이다. 다른 후보와 비교하거나
이 대응안의 최종 채택 여부를 판단하지 마라 -- 이 검토는 우려사항을 드러낼 뿐 정답을 단정하지
않는다.

## 대응안
유형: {candidate.candidate_type}
설명: {candidate.description}
선행조건: {candidate.preconditions}
착수 시점: {candidate.start_time_variant}
검증상태(제약검증 결과): {candidate.validation_status}
제외사유(있는 경우): {candidate.exclusion_category} / {candidate.exclusion_detail}

## 현재 운영 스냅샷
{snapshot_summary}

## 지시사항
- 제약 검증 단계가 이미 확인한 "자원 용량/비용 한도/계약 조건" 같은 정량적 항목은 다시 확인하지
  마라. 대신 담당 조직 간 커뮤니케이션 공백, 착수 시점과 실제 운영 상태(operational_state) 사이의
  타이밍 불일치, 여러 부서의 동시 조율이 필요한데 이 대응안에 명시된 선행조건에는 나타나지 않는
  조율 리스크를 찾아 flags 배열에 문자열로 나열하라 (없으면 빈 배열).
- concern_level은 low/medium/high 중 하나로 답하라.
- comment에는 반드시 판단 근거를 채워라. 근거 없는 빈 문장은 허용되지 않는다.
- 반드시 아래 JSON 스키마 하나만 응답하라. 다른 설명 텍스트나 마크다운 코드펜스를 붙이지 마라.

{{"concern_level": "low", "comment": "string", "flags": ["string"]}}
"""


def _build_risk_lens_prompt(candidate: ResponseCandidate, sim: SimulationResult) -> str:
    return f"""당신은 공급망 위기대응 도구의 "다중 관점 교차검증" 중 리스크(risk) 관점 검토자다.
이 대응안의 민감도 변수·가정·신뢰도만 검토해서, 신뢰도가 실제로 깔린 가정의 개수/성격에 비해
과도하게 높게 잡혀 있는지, 혹은 드러나지 않은 불확실성이 있는지를 찾아라. 다른 후보와 비교하거나
이 대응안의 최종 채택 여부를 판단하지 마라 -- 이 검토는 우려사항을 드러낼 뿐 정답을 단정하지
않는다.

## 대응안
유형: {candidate.candidate_type}
설명: {candidate.description}

## 시뮬레이션 결과
신뢰도(confidence, 0~1): {sim.confidence}
핵심 민감도 변수(sensitivity_variables): {sim.sensitivity_variables}
assumption (LLM이 명시한 가정): {sim.assumption}
inference (DAG 경로로 추론한 값): {sim.inference}

## 지시사항
- assumption에 담긴 가정의 개수가 많거나, 가정 하나가 결과 전체를 좌우할 만큼 결정적인데도
  confidence가 높게(예: 0.8 이상) 잡혀 있다면 과신(overconfident)으로 보고 flags에 구체적으로
  나열하라.
- sensitivity_variables에 나열된 변수들이 실제로는 서로 연동되어 있거나(하나가 나빠지면 다른
  것도 같이 나빠짐), 시뮬레이션이 명시하지 않은 숨은 불확실성(예: 대체 경로 자체의 가용성)이
  있다면 그것도 flags에 나열하라. 우려사항이 없으면 flags는 빈 배열로 답하라.
- concern_level은 low/medium/high 중 하나로 답하라.
- comment에는 반드시 판단 근거를 채워라. 근거 없는 빈 문장은 허용되지 않는다.
- 반드시 아래 JSON 스키마 하나만 응답하라. 다른 설명 텍스트나 마크다운 코드펜스를 붙이지 마라.

{{"concern_level": "low", "comment": "string", "flags": ["string"]}}
"""


def _build_lens_prompts(
    candidate: ResponseCandidate, sim: SimulationResult, snapshot: OperationalSnapshot | None
) -> dict[str, str]:
    return {
        LENS_COST: _build_cost_lens_prompt(candidate, sim),
        LENS_FEASIBILITY: _build_feasibility_lens_prompt(candidate, sim, snapshot),
        LENS_RISK: _build_risk_lens_prompt(candidate, sim),
    }


def _parse_lens_result(raw_text: str) -> LensReviewResult:
    data = extract_json(raw_text)
    return LensReviewResult.model_validate(data)


async def _generate_and_parse_with_retry(
    provider: LLMProvider, prompt: str, label: str
) -> LensReviewResult:
    last_error: Exception | None = None
    for _attempt in range(2):  # initial try + 1 retry, same contract as simulation.py
        try:
            raw = await asyncio.to_thread(provider.generate, prompt)
            return _parse_lens_result(raw)
        except (json.JSONDecodeError, ValidationError, ValueError, GeminiAPIError, ClaudeCLIError) as exc:
            last_error = exc
            continue
    raise CandidateReviewError(
        f"'{label}' 교차검증 응답 생성에 실패했습니다(1회 재시도 후에도 실패): {last_error}"
    )


async def review_candidate(
    db: Session,
    candidate: ResponseCandidate,
    simulation_result: SimulationResult,
    llm_provider: LLMProvider | None = None,
) -> list[CandidateReview]:
    """Runs the 3 independent lens reviews for one candidate in parallel
    (`asyncio.gather`) and appends one row per lens to `candidate_reviews`.
    Raises `CandidateReviewError` if any single lens's response fails
    validation even after its own retry -- the whole call fails rather than
    silently persisting 2 of 3 lenses, so a candidate's review set is never
    partially written."""

    provider = llm_provider or get_llm_provider()
    snapshot = OperationalSnapshotRepository(db).get(candidate.snapshot_id)
    prompts = _build_lens_prompts(candidate, simulation_result, snapshot)
    label = f"{candidate.candidate_type}#{candidate.id}"

    parsed_results = await asyncio.gather(
        *[_generate_and_parse_with_retry(provider, prompts[lens], f"{label}/{lens}") for lens in LENSES]
    )

    review_repo = CandidateReviewRepository(db)
    reviews: list[CandidateReview] = []
    for lens, parsed in zip(LENSES, parsed_results):
        reviews.append(
            review_repo.add(
                candidate_id=candidate.id,
                incident_id=candidate.incident_id,
                simulation_result_id=simulation_result.id,
                lens=lens,
                concern_level=parsed.concern_level,
                comment=parsed.comment,
                flags=parsed.flags,
            )
        )
    return reviews


async def review_candidates_for_incident(
    db: Session, incident_id: int, llm_provider: LLMProvider | None = None
) -> list[CandidateReview]:
    """Stage 4 of the simulate pipeline. Every candidate under `incident_id`
    that has a latest simulation result (via
    `SimulationResultRepository.latest_for_candidate`) gets reviewed; a
    candidate with no simulation result at all is excluded entirely (never
    sent to the LLM), same "no simulation, no downstream analysis" rule as
    `simulate_candidates` applies to 불가능 candidates. Candidates are
    reviewed in parallel via `asyncio.gather` (and each candidate's own 3
    lenses are, in turn, parallel too -- nested parallelism, intentional).
    Raises IncidentNotFoundError if the incident does not exist."""

    incident = IncidentRepository(db).get(incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"incident {incident_id} not found")

    candidate_repo = ResponseCandidateRepository(db)
    sim_repo = SimulationResultRepository(db)

    targets: list[tuple[ResponseCandidate, SimulationResult]] = []
    for candidate in candidate_repo.for_incident(incident_id):
        latest_sim = sim_repo.latest_for_candidate(candidate.id)
        if latest_sim is not None:
            targets.append((candidate, latest_sim))

    if not targets:
        return []

    provider = llm_provider or get_llm_provider()

    per_candidate_reviews = await asyncio.gather(
        *[review_candidate(db, candidate, sim, llm_provider=provider) for candidate, sim in targets]
    )

    all_reviews: list[CandidateReview] = []
    for reviews in per_candidate_reviews:
        all_reviews.extend(reviews)
    return all_reviews
