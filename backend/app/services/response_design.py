"""대응 설계 에이전트 (agents/response-design.md).

Stage 1 of the POST /incidents/{id}/simulate pipeline: turns an incident's
Impact DAG + past SOP/계약/플레이북 search results into a broad list of
`response_candidates` rows. This stage never judges feasibility (that is
constraint-validation's job, stage 2) -- everything produced here is stored
with validation_status='미검증'.

Two hard rules from the persona doc:
  1. A deterministic, LLM-free baseline (무대응) candidate is always
     produced -- if it were ever missing, avoided-loss calculations in later
     stages would have nothing to compare against.
  2. Every non-baseline candidate must be able to point at the reference
     documents it actually used, and a candidate must still be produced even
     when RAG returns zero hits (reference_document_ids=[] in that case).

LLM call handling: `provider.generate()` is a synchronous, blocking network
call (Gemini API / Claude CLI). This function is `async def` and wraps that
call in `asyncio.to_thread` so a single response-design call does not block
the FastAPI event loop while waiting on the LLM -- other requests being
served by the same process (e.g. someone polling a different incident) are
not held up behind it. This is the only genuinely blocking I/O in this
stage; the DB repository calls around it stay plain synchronous SQLAlchemy
calls (local Postgres queries are fast and are not the bottleneck here).
"""

from __future__ import annotations

import asyncio
import json

from sqlalchemy.orm import Session

from app.llm import LLMProvider, get_llm_provider
from app.llm.json_utils import extract_json
from app.models.incident import Incident
from app.models.operational_snapshot import OperationalSnapshot
from app.models.response_candidate import ResponseCandidate
from app.rag.search import search_similar_chunks
from app.repositories.impact_dag import ImpactDagEdgeRepository, ImpactDagNodeRepository
from app.repositories.incidents import IncidentRepository
from app.repositories.response_candidates import ResponseCandidateRepository
from app.services.operational_graph import (
    IncidentNotEligibleError,  # re-exported for API layer convenience
    IncidentNotFoundError,  # re-exported for API layer convenience
    ensure_snapshot_and_dag,
)

__all__ = [
    "generate_candidates",
    "ResponseGenerationError",
    "IncidentNotFoundError",
    "IncidentNotEligibleError",
    "BASELINE_CANDIDATE_TYPE",
]

RAG_DOC_TYPES = ["사고", "플레이북", "SOP", "계약"]
RAG_TOP_K = 5

BASELINE_CANDIDATE_TYPE = "baseline"
START_TIME_VARIANT_VALUES = {"now", "+6h"}

# db/init/002-schema.sql: response_candidates.candidate_type has a DB CHECK
# constraint restricting it to exactly these 3 values -- '단일'/'복합' only
# distinguish single- vs multi-action responses, they are NOT the specific
# response category (컨테이너 우선반출/긴급운송/... from
# simulation-supply-chain-tool.md §4.2). The LLM is asked for both a
# constrained candidate_type and a free-text response_category; the latter
# is folded into `description` as a "[카테고리] ..." prefix so it survives
# without needing a schema migration, and so constraint-validation's
# keyword-based resource heuristics (which scan `description`) still see it.
ALLOWED_LLM_CANDIDATE_TYPES = {"단일", "복합"}


class ResponseGenerationError(RuntimeError):
    """The LLM's candidate-generation response could not be parsed into a
    valid candidate list even after one retry."""


# ------------------------------------------------------------------
# Prompt construction (Impact DAG path + RAG results -> single prompt,
# ARCHITECTURE.md §4 steps 1-2 applied to candidate generation)
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
        return "(참고할 과거 사고/SOP/계약/플레이북 검색 결과 없음 — 근거 없이 대응안을 생성해야 함)"
    lines = []
    for r in rag_results:
        snippet = (r.get("chunk_text") or "")[:300]
        lines.append(
            f"- document_id={r.get('document_id')} [{r.get('doc_type')}] {r.get('title')}: {snippet}"
        )
    return "\n".join(lines)


def _query_text_for_incident(incident: Incident) -> str:
    affected = incident.affected_targets or {}
    parts = ", ".join(affected.get("parts") or [])
    containers = ", ".join(affected.get("containers") or [])
    return f"{incident.type} {incident.location} 대응 방안 - 부품: {parts} 컨테이너: {containers}"


def _build_prompt(incident: Incident, dag_summary: str, rag_summary: str) -> str:
    return f"""당신은 공급망 위기대응 도구의 "대응 설계 에이전트"다. 아래 사건에 대해 실행 가능한
대응안 후보를 JSON으로 생성하라. 이 단계에서는 실행 가능성을 판단하지 않는다 — 이론적으로
가능한 선택지를 넓게 만드는 데 집중하라 (실행 가능성 검증은 다음 단계 책임이다).

## 사건
유형: {incident.type}
위치: {incident.location}
발생시각: {incident.occurred_at}

## Impact DAG 경로 (영향 전파 경로)
{dag_summary}

## 참고 문서 검색 결과 (과거 사고 / SOP / 계약 / 플레이북)
{rag_summary}

## 지시사항
- 컨테이너 우선반출, 긴급운송, 대체항/경로, 생산순서변경, 대체부품/안전재고 전환,
  고객별 출고 우선순위 조정 중에서 서로 다른 유형의 대응안을 최소 3개 생성하라.
  (baseline/무대응 후보는 이미 별도로 생성되므로 여기서 만들지 마라.)
- 그 중 최소 한 묶음은 동일한 대응을 착수 시점만 다르게 한 변형으로 2개 만들어라
  (start_time_variant: "now" = 지금 즉시 착수, "+6h" = 6시간 후 착수).
- 각 후보가 위 참고 문서 중 실제로 근거로 삼은 항목이 있다면 그 document_id를
  reference_document_ids 배열에 넣어라. 근거로 삼은 문서가 없으면 빈 배열로 두어라.
- response_category에는 대응 유형(컨테이너 우선반출/긴급운송/대체항/생산순서변경/대체부품/
  고객출고우선순위 중 하나)을, candidate_type에는 단일 조치인지 복합 조치(여러 조치를 동시에
  실행)인지를 "단일" 또는 "복합" 중 하나로만 넣어라 (다른 값 금지).
- 반드시 아래 JSON 스키마 하나만 응답하라. 다른 설명 텍스트나 마크다운 코드펜스를 붙이지 마라.

{{"candidates": [
  {{
    "response_category": "컨테이너 우선반출 | 긴급운송 | 대체항 | 생산순서변경 | 대체부품 | 고객출고우선순위",
    "candidate_type": "단일 | 복합",
    "description": "구체적인 대응 설명",
    "preconditions": ["선행조건 문자열", "..."],
    "start_time_variant": "now" 또는 "+6h" 또는 null,
    "reference_document_ids": [123]
  }}
]}}
"""


# ------------------------------------------------------------------
# LLM response parsing
# ------------------------------------------------------------------


def _parse_llm_candidates(raw_text: str) -> list[dict]:
    data = extract_json(raw_text)
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        raise ValueError("응답 JSON에 'candidates' 배열이 없습니다")
    candidates = data["candidates"]
    for c in candidates:
        if not isinstance(c, dict) or not c.get("description"):
            raise ValueError("각 후보는 최소한 description 필드를 가진 객체여야 합니다")
    return candidates


def _ensure_start_time_variants(candidates: list[dict]) -> list[dict]:
    """§5.1의 "지금 대응 / 6시간 후 대응 / 무대응 비교"에는 최소 한 쌍의
    now/+6h 변형이 항상 있어야 한다. LLM이 프롬프트 지시를 따르지 않는
    경우를 대비해, 그런 변형이 하나도 없으면 첫 번째 후보를 결정적으로
    복제해 now/+6h 쌍을 만든다."""

    if not candidates:
        return candidates
    if any(c.get("start_time_variant") in START_TIME_VARIANT_VALUES for c in candidates):
        return candidates

    first = dict(candidates[0])
    first["start_time_variant"] = "now"
    twin = dict(first)
    twin["start_time_variant"] = "+6h"
    twin["description"] = f"{first.get('description', '')} (착수 시점을 6시간 후로 지연)"
    return [first, *candidates[1:], twin]


# ------------------------------------------------------------------
# Baseline (deterministic, no LLM call)
# ------------------------------------------------------------------


def _make_baseline_fields(incident: Incident, snapshot: OperationalSnapshot) -> dict:
    return dict(
        incident_id=incident.id,
        snapshot_id=snapshot.id,
        candidate_type=BASELINE_CANDIDATE_TYPE,
        description="무대응 - 현재 계획대로 진행하며 재고 소진 시 자연 발생하는 라인정지/납기지연을 수용",
        reference_document_ids=[],
        preconditions=[],
        start_time_variant="즉시",
        validation_status="미검증",
    )


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------


async def generate_candidates(
    db: Session, incident_id: int, llm_provider: LLMProvider | None = None
) -> list[ResponseCandidate]:
    """Stage 1 of the simulate pipeline. Always produces a baseline
    candidate first (deterministic, no LLM call), then asks the LLM for the
    rest. Raises IncidentNotFoundError / IncidentNotEligibleError (from
    ensure_snapshot_and_dag) or ResponseGenerationError (LLM response could
    not be parsed after one retry)."""

    # ensure_snapshot_and_dag both validates the incident (404/409 cases)
    # and is the only way to obtain the snapshot this stage's candidates
    # are pinned to (agents/operational-graph.md's lazy-create contract).
    snapshot = ensure_snapshot_and_dag(db, incident_id)
    incident = IncidentRepository(db).get(incident_id)
    assert incident is not None  # guaranteed by ensure_snapshot_and_dag succeeding

    candidate_repo = ResponseCandidateRepository(db)
    created: list[ResponseCandidate] = [candidate_repo.add(**_make_baseline_fields(incident, snapshot))]

    provider = llm_provider or get_llm_provider()

    dag_summary = _dag_path_summary(db, snapshot.id)
    rag_results = search_similar_chunks(
        db, _query_text_for_incident(incident), doc_types=RAG_DOC_TYPES, top_k=RAG_TOP_K
    )
    rag_summary = _rag_summary(rag_results)
    prompt = _build_prompt(incident, dag_summary, rag_summary)

    # provider.generate() is a synchronous blocking call (network round-trip
    # to Gemini/Claude CLI) -- run it off the event loop via to_thread so
    # this async endpoint does not stall other requests while waiting.
    raw = await asyncio.to_thread(provider.generate, prompt)
    try:
        llm_candidates = _parse_llm_candidates(raw)
    except (ValueError, json.JSONDecodeError):
        raw = await asyncio.to_thread(provider.generate, prompt)
        try:
            llm_candidates = _parse_llm_candidates(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ResponseGenerationError(
                f"대응안 후보 생성 LLM 응답을 파싱하지 못했습니다(1회 재시도 후에도 실패): {exc}"
            ) from exc

    llm_candidates = _ensure_start_time_variants(llm_candidates)

    # Never trust the LLM's claimed reference_document_ids at face value --
    # intersect with the document_ids that RAG actually returned so a
    # hallucinated reference can't slip through, and so a zero-hit RAG
    # search always yields reference_document_ids=[] regardless of what the
    # LLM claims.
    rag_document_ids = {r["document_id"] for r in rag_results}

    for c in llm_candidates:
        raw_ids = c.get("reference_document_ids") or []
        sanitized_ids = [doc_id for doc_id in raw_ids if doc_id in rag_document_ids]

        candidate_type = c.get("candidate_type")
        if candidate_type not in ALLOWED_LLM_CANDIDATE_TYPES:
            candidate_type = "단일"

        # response_category (컨테이너 우선반출/긴급운송/... -- the actual
        # business-spec response type, §4.2) has no column of its own
        # (candidate_type is DB-constrained to 단일/복합/baseline only), so
        # it is folded into description as a "[카테고리] ..." prefix.
        response_category = c.get("response_category")
        description = c["description"]
        if response_category and response_category not in ALLOWED_LLM_CANDIDATE_TYPES:
            description = f"[{response_category}] {description}"

        created.append(
            candidate_repo.add(
                incident_id=incident.id,
                snapshot_id=snapshot.id,
                candidate_type=candidate_type,
                description=description,
                reference_document_ids=sanitized_ids,
                preconditions=c.get("preconditions") or [],
                start_time_variant=c.get("start_time_variant"),
                validation_status="미검증",
            )
        )

    return created
