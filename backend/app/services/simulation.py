"""시뮬레이션 에이전트 (agents/simulation.md).

Stage 3 of the POST /incidents/{id}/simulate pipeline: for every candidate
that constraint-validation passed (가능/조건부 -- 불가능 candidates are never
simulated), combines the Impact DAG path, RAG search results, and the
current operational snapshot into one LLM prompt (ARCHITECTURE.md §4) and
asks the LLM to produce expected loss / P90 / CVaR / sensitivity variables /
confidence, with FACT/INFERENCE/ASSUMPTION enforced as top-level fields by
a Pydantic schema (`SimulationLLMResult` below) -- a response with only
free-text justification is rejected, not just "accepted with a warning".

`simulation_results` is append-only (see app/repositories/simulation_results.py
-- there is no update() method to call even by mistake); every call to this
function inserts new rows and never touches a prior result, so re-running
the pipeline for the same incident is always a new "version" rather than a
correction of the old one.

Async / parallelism: `provider.generate()` is a synchronous, blocking call.
This function is `async def` and fires all eligible candidates' LLM calls
concurrently via `asyncio.gather` + `asyncio.to_thread` (ARCHITECTURE.md §4,
agents/simulation.md work item #3) -- this is both what makes
`POST /incidents/{id}/simulate` fast with N candidates instead of N times
the latency of one, and what keeps a single slow LLM call from blocking the
event loop for the rest of the process. The DB repository calls that
prepare each prompt and persist each result stay plain synchronous
SQLAlchemy calls before/after the gather (never inside a concurrently-
awaited task), since one Session is not safe to use concurrently from
multiple tasks.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.llm import LLMProvider, get_llm_provider
from app.llm.json_utils import extract_json
from app.models.operational_snapshot import OperationalSnapshot
from app.models.response_candidate import ResponseCandidate
from app.models.simulation_result import SimulationResult
from app.rag.search import search_similar_chunks
from app.repositories.impact_dag import ImpactDagEdgeRepository, ImpactDagNodeRepository
from app.repositories.incidents import IncidentRepository
from app.repositories.operational_snapshots import OperationalSnapshotRepository
from app.repositories.response_candidates import ResponseCandidateRepository
from app.repositories.simulation_results import SimulationResultRepository
from app.services.operational_graph import IncidentNotFoundError

__all__ = ["simulate_candidates", "SimulationValidationError", "IncidentNotFoundError", "SimulationLLMResult"]

RAG_DOC_TYPES = ["사고", "플레이북", "SOP", "계약"]
RAG_TOP_K = 5

ELIGIBLE_VALIDATION_STATUSES = ("가능", "조건부")


class SimulationValidationError(RuntimeError):
    """The LLM's simulation response could not be parsed/validated against
    the required schema, even after one retry."""


# ------------------------------------------------------------------
# Response schema -- FACT/INFERENCE/ASSUMPTION enforced at the schema
# level (agents/simulation.md work item #1): a response missing any of the
# three, or providing an empty object for one, fails validation just like a
# missing numeric field would.
# ------------------------------------------------------------------


class SimulationLLMResult(BaseModel):
    expected_loss: float = Field(ge=0)
    p90: float = Field(ge=0)
    cvar: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    sensitivity_variables: list[str] = Field(min_length=1)
    fact: dict[str, Any]
    inference: dict[str, Any]
    assumption: dict[str, Any]

    @field_validator("fact", "inference", "assumption")
    @classmethod
    def _must_not_be_empty(cls, value: dict, info):
        if not value:
            raise ValueError(
                f"{info.field_name} 필드는 최소 1개 이상의 근거를 담아야 합니다 "
                "(자유 텍스트 근거만 있는 응답은 허용되지 않음)"
            )
        return value


# ------------------------------------------------------------------
# Prompt construction
# ------------------------------------------------------------------


def _dag_path_summary(db: Session, snapshot_id: int) -> str:
    nodes = ImpactDagNodeRepository(db).for_snapshot(snapshot_id)
    edges = ImpactDagEdgeRepository(db).for_snapshot(snapshot_id)
    nodes_by_id = {n.id: n for n in nodes}

    node_lines = [
        f"- [{n.node_key}] {n.label} (영향대상: {n.affected_target}, 예상시각: {n.expected_time}, "
        f"근거: {n.basis}, 불확실성: {n.uncertainty})"
        for n in nodes
    ]
    edge_lines = []
    for e in edges:
        from_node = nodes_by_id.get(e.from_node_id)
        to_node = nodes_by_id.get(e.to_node_id)
        if from_node and to_node:
            edge_lines.append(f"- {from_node.node_key} -> {to_node.node_key}: {e.basis}")

    return "노드:\n" + "\n".join(node_lines) + "\n엣지:\n" + "\n".join(edge_lines)


def _rag_summary(rag_results: list[dict]) -> str:
    if not rag_results:
        return "(참고할 과거 사고/SOP/계약/플레이북 검색 결과 없음)"
    lines = []
    for r in rag_results:
        snippet = (r.get("chunk_text") or "")[:300]
        lines.append(
            f"- document_id={r.get('document_id')} [{r.get('doc_type')}] {r.get('title')}: {snippet}"
        )
    return "\n".join(lines)


def _query_text_for_candidate(candidate: ResponseCandidate) -> str:
    return f"{candidate.candidate_type} {candidate.description}"


def _build_simulation_prompt(
    candidate: ResponseCandidate, snapshot: OperationalSnapshot, dag_summary: str, rag_results: list[dict]
) -> str:
    rag_summary = _rag_summary(rag_results)
    operational_state_json = json.dumps(snapshot.operational_state, ensure_ascii=False, default=str)

    return f"""당신은 공급망 위기대응 도구의 "시뮬레이션 에이전트"다. 아래 대응안 단 하나에 대해
독립적인 what-if 손실 예측을 수행하라. 다른 후보와 비교하거나 순위를 매기지 마라 -- 그건
이 단계의 책임이 아니다.

## 대응안
유형: {candidate.candidate_type}
설명: {candidate.description}
착수 시점: {candidate.start_time_variant}
선행조건/검증상태: {candidate.validation_status} / {candidate.preconditions}

## Impact DAG 경로 (영향 전파 경로)
{dag_summary}

## 참고 문서 검색 결과 (과거 사고 / SOP / 계약 / 플레이북)
{rag_summary}

## 현재 운영 스냅샷 (data_version={snapshot.data_version}, scenario_version={snapshot.scenario_version})
{operational_state_json}

## 지시사항
- 이 대응안을 적용했을 때의 기대손실(expected_loss), P90 손실(p90), CVaR(cvar, 화폐 단위 숫자),
  신뢰도(confidence, 0~1 사이 소수), 핵심 민감도 변수(sensitivity_variables, 문자열 배열, 최소 1개)를
  산출하라.
- 근거는 반드시 다음 세 구분으로 나눠 채워라. 각각 최소 1개 이상의 key-value 쌍을 포함해야 하며,
  자유 텍스트 문단 하나만 넣는 것은 허용되지 않는다.
  - fact: 위 운영 스냅샷에서 그대로 가져온 값
  - inference: Impact DAG 경로로 추론한 값
  - assumption: 네가 명시적으로 가정한 값
- 반드시 아래 JSON 스키마 하나만 응답하라. 다른 설명 텍스트나 마크다운 코드펜스를 붙이지 마라.

{{"expected_loss": 0, "p90": 0, "cvar": 0, "confidence": 0.0,
  "sensitivity_variables": ["string"],
  "fact": {{"key": "value"}}, "inference": {{"key": "value"}}, "assumption": {{"key": "value"}}}}
"""


def _parse_llm_result(raw_text: str) -> SimulationLLMResult:
    data = extract_json(raw_text)
    return SimulationLLMResult.model_validate(data)


async def _generate_and_parse_with_retry(
    provider: LLMProvider, prompt: str, candidate_label: str
) -> SimulationLLMResult:
    last_error: Exception | None = None
    for _attempt in range(2):  # initial try + 1 retry, per agents/simulation.md DoD
        raw = await asyncio.to_thread(provider.generate, prompt)
        try:
            return _parse_llm_result(raw)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            continue
    raise SimulationValidationError(
        f"후보 '{candidate_label}' 시뮬레이션 응답이 스키마를 위반했습니다"
        f"(1회 재시도 후에도 실패): {last_error}"
    )


async def simulate_candidates(
    db: Session, incident_id: int, llm_provider: LLMProvider | None = None
) -> list[SimulationResult]:
    """Stage 3 of the simulate pipeline. Only candidates whose
    validation_status is 가능 or 조건부 are simulated -- 불가능 candidates are
    skipped entirely (never sent to the LLM). Raises IncidentNotFoundError if
    the incident does not exist, and SimulationValidationError if any
    eligible candidate's LLM response cannot be parsed/validated against
    `SimulationLLMResult` even after one retry (the whole call fails rather
    than silently skipping that candidate -- a loss estimate must always be
    backed by a schema-conformant fact/inference/assumption breakdown)."""

    incident = IncidentRepository(db).get(incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"incident {incident_id} not found")

    candidate_repo = ResponseCandidateRepository(db)
    eligible = [c for c in candidate_repo.for_incident(incident_id) if c.validation_status in ELIGIBLE_VALIDATION_STATUSES]
    if not eligible:
        return []

    provider = llm_provider or get_llm_provider()
    snapshot_repo = OperationalSnapshotRepository(db)

    # Build every prompt synchronously (DB reads) *before* the concurrent
    # LLM calls -- only the network round-trips run inside the gather.
    prepared: list[tuple[ResponseCandidate, OperationalSnapshot, str]] = []
    for candidate in eligible:
        snapshot = snapshot_repo.get(candidate.snapshot_id)
        if snapshot is None:
            continue
        dag_summary = _dag_path_summary(db, candidate.snapshot_id)
        rag_results = search_similar_chunks(
            db, _query_text_for_candidate(candidate), doc_types=RAG_DOC_TYPES, top_k=RAG_TOP_K
        )
        prompt = _build_simulation_prompt(candidate, snapshot, dag_summary, rag_results)
        prepared.append((candidate, snapshot, prompt))

    if not prepared:
        return []

    parsed_results = await asyncio.gather(
        *[
            _generate_and_parse_with_retry(provider, prompt, f"{candidate.candidate_type}#{candidate.id}")
            for candidate, _snapshot, prompt in prepared
        ]
    )

    sim_repo = SimulationResultRepository(db)
    results: list[SimulationResult] = []
    for (candidate, snapshot, _prompt), parsed in zip(prepared, parsed_results):
        results.append(
            sim_repo.add(
                candidate_id=candidate.id,
                incident_id=incident_id,
                expected_loss=parsed.expected_loss,
                p90=parsed.p90,
                cvar=parsed.cvar,
                sensitivity_variables=parsed.sensitivity_variables,
                confidence=parsed.confidence,
                fact=parsed.fact,
                inference=parsed.inference,
                assumption=parsed.assumption,
                data_version=snapshot.data_version,
                scenario_version=snapshot.scenario_version,
            )
        )

    return results
