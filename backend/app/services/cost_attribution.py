"""비용 귀속 분류 (agents/post-report.md work item #3,
simulation-supply-chain-tool.md §9).

LD(지연배상금)/D&D(체선·체화료) 절감액을 하나로 합산하지 않고 3가지로 분리한다:
직접 손익 효과(당사 부담 절감) / 고객 회피비용(화주 부담 절감) / 분쟁·협상
가능 금액(귀책 판단에 따라 부담 주체가 달라질 수 있는 금액).

**이 모듈은 법무 판단을 대체하지 않는다.** `search_similar_chunks`로 계약
조항(`doc_types=["계약"]`)을 검색해 LD/D&D 관련 조항이 실제로 존재하는지만
확인하는 휴리스틱 키워드 매칭이다 -- 조항의 실제 귀책 주체 지정 여부, 이 사건의
지연이 누구 책임인지는 이 모듈이 판단하지 않는다(그런 판단을 할 데이터 자체가
없다: 사건-계약 당사자 매핑, 귀책 판정 이력 등이 이 코드베이스에 없다).

분류 원칙 (근거 없이 "직접손익"으로 단정하지 않기 위한 설계):
  - LD/D&D 조항을 아예 찾지 못하면(계약 문서 자체가 이 사건과 연결되지
    않았거나 조항이 없음) -> 전액 "분쟁·협상 가능 금액"(안전한 기본값).
  - D&D 조항만 발견되면 -> §9 원칙("D&D는 화주가 부담하는 경우가 많다")에
    따라 전액 "고객 회피비용"으로 분류하되, 이것도 확정이 아니라 휴리스틱
    기본값임을 명시한다.
  - LD 조항이 발견되면(단독이든 D&D와 함께든) -> "LD는 계약상 귀책 주체가
    부담한다"는 원칙 자체가 귀책 주체가 당사인지 화주인지 제3자인지를 특정하지
    않고, 이 시스템에는 실제 지연의 귀책을 판단하는 로직/데이터가 없으므로
    "분쟁·협상 가능 금액"으로 분류한다.
  - "직접 손익 효과"는 이 휴리스틱만으로는 절대 0을 넘지 않는다 -- 계약 조항
    키워드 매칭만으로 "당사가 실제로 이 비용을 부담한다"를 단정할 근거가 없기
    때문이다(작업 브리핑의 명시적 지시: "근거 없이 비용을 '직접손익'으로
    분류하지 마라"). 실제 당사 부담분이 있다면 법무 검토 후 사람이 재분류한다.

모든 함수는 동기(`def`)다 -- `search_similar_chunks`가 임베딩 API를 딱 한 번
블로킹 호출하지만 반복 호출도 아니고, LLM 텍스트 생성 호출이 전혀 없어
CLAUDE.md 비동기 처리 원칙상 async로 감쌀 실익이 없다(이 웨이브는 LLM 호출이
전혀 없는 순수 집계/분류 웨이브).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.llm.gemini_api import GeminiAPIError
from app.rag.search import EmbedFn, search_similar_chunks
from app.repositories.decision_packages import DecisionPackageRepository
from app.repositories.incidents import IncidentRepository
from app.repositories.response_candidates import ResponseCandidateRepository
from app.repositories.simulation_results import SimulationResultRepository
from app.services.operational_graph import IncidentNotFoundError  # re-exported for API layer

__all__ = [
    "classify_cost_attribution",
    "compute_expected_avoided_loss",
    "baseline_candidate_with_earliest_sim",
    "final_approved_candidate",
    "IncidentNotFoundError",
    "DIRECT_PL_KEY",
    "CUSTOMER_AVOIDANCE_KEY",
    "DISPUTE_NEGOTIABLE_KEY",
]

BASELINE_CANDIDATE_TYPE = "baseline"

# 계약 조항 청크 텍스트에서 LD/D&D 조항 존재 여부를 판별하는 키워드. 실제
# 법률 용어 매칭이 아니라 대략적인 신호일 뿐이다 -- rag/chunking.py의 계약
# 청킹은 조항 단위(제N조)이므로 청크 텍스트 안에 이 키워드가 있으면 그 조항이
# LD/D&D를 다룬다고 본다.
LD_KEYWORDS: tuple[str, ...] = ("지연배상", "지체상금", "지체배상", "LD")
DND_KEYWORDS: tuple[str, ...] = ("체선료", "체화료", "체선체화", "D&D", "demurrage", "detention")

DIRECT_PL_KEY = "직접_손익_효과"
CUSTOMER_AVOIDANCE_KEY = "고객_회피비용"
DISPUTE_NEGOTIABLE_KEY = "분쟁_협상_가능_금액"


def _matches_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(k.lower() in text.lower() for k in keywords)


def _to_float(value: Any) -> float | None:
    return float(value) if value is not None else None


# ------------------------------------------------------------------
# baseline / 승인 후보 조회 -- post_report.py와 공유하는 헬퍼.
# ------------------------------------------------------------------


def baseline_candidate_with_earliest_sim(db: Session, incident_id: int):
    """baseline 후보와 **그 후보의 가장 이른(첫) 시뮬레이션 결과**를 반환한다.

    회피손실 계산은 "실제 결과와 당시 계산한 무대응 baseline의 차이"로
    산출해야 하고, baseline의 데이터 버전·가정·계산시각을 고정해 사후에 유리한
    기준으로 재계산하지 못하게 해야 한다(simulation-supply-chain-tool.md §9).
    그래서 여기서는 `SimulationResultRepository.latest_for_candidate`(가장
    최근 버전)를 의도적으로 쓰지 않고, `for_incident`가 이미 created_at
    오름차순으로 반환하는 것을 이용해 이 candidate_id의 첫 레코드를 고른다."""

    candidate = ResponseCandidateRepository(db).baseline_for_incident(incident_id)
    if candidate is None:
        return None, None

    sim = None
    for row in SimulationResultRepository(db).for_incident(incident_id):
        if row.candidate_id == candidate.id:
            sim = row
            break
    return candidate, sim


def final_approved_candidate(db: Session, incident_id: int):
    """"최종 승인 후보" -- decision_packages의 가장 최근 패키지가 순위화한
    ranked_candidates 중 baseline이 아닌 1순위(response_optimization.
    rank_candidates가 이미 composite_score 오름차순으로 정렬해 둔 것).
    approvals 테이블 자체에는 "이 후보를 승인했다"는 필드가 없어, 이 휴리스틱은
    app/services/communication.py의 `_build_message_context`가 SOP 발송 대상을
    고르는 것과 동일한 판단 근거를 재사용한다(코드베이스 전체에서 이미 쓰이고
    있는 관례)."""

    package = DecisionPackageRepository(db).latest_for_incident(incident_id)
    if package is None:
        return None, None

    ranked = ((package.package.get("ranked_candidates") or {}).get("ranked")) or []
    top = next((r for r in ranked if r.get("candidate_type") != BASELINE_CANDIDATE_TYPE), None)
    if top is None and ranked:
        top = ranked[0]
    if top is None or top.get("candidate_id") is None:
        return None, None

    candidate = ResponseCandidateRepository(db).get(top["candidate_id"])
    if candidate is None:
        return None, None
    sim = SimulationResultRepository(db).latest_for_candidate(candidate.id)
    return candidate, sim


def _candidate_ref(candidate, sim) -> dict[str, Any] | None:
    if candidate is None:
        return None
    return {
        "candidate_id": candidate.id,
        "candidate_type": candidate.candidate_type,
        "description": candidate.description,
        "expected_loss": _to_float(sim.expected_loss) if sim is not None else None,
        "data_version": sim.data_version if sim is not None else None,
        "scenario_version": sim.scenario_version if sim is not None else None,
        "calculated_at": sim.created_at if sim is not None else None,
        "has_simulation_result": sim is not None,
    }


def compute_expected_avoided_loss(db: Session, incident_id: int) -> dict[str, Any]:
    """"예상 회피손실" = baseline 후보의 (고정된, 첫) 기대손실 - 승인된 후보의
    (최신) 기대손실. 실측 회피손실이 아니라 추정치이므로 필드명/설명에 항상
    "예상"이라는 표현을 명시한다 (작업 브리핑 스코프 결정).

    baseline 또는 승인 후보 중 하나라도 없거나 시뮬레이션 결과가 없으면
    `available=False`와 구체적인 사유를 반환한다 -- 절대 0이나 임의값으로
    채우지 않는다(DoD case 2: baseline 레코드가 없는 예외 상황)."""

    baseline_candidate, baseline_sim = baseline_candidate_with_earliest_sim(db, incident_id)
    approved_candidate, approved_sim = final_approved_candidate(db, incident_id)

    missing: list[str] = []
    if baseline_candidate is None:
        missing.append("baseline 후보(response_candidates.candidate_type='baseline')가 없음")
    elif baseline_sim is None:
        missing.append("baseline 후보의 시뮬레이션 결과(simulation_results)가 없음")

    if approved_candidate is None:
        missing.append(
            "승인된(비-baseline) 후보를 decision_packages의 ranked_candidates에서 찾을 수 없음 "
            "(decision_package가 아직 생성되지 않았거나, 순위화된 비-baseline 후보가 없음)"
        )
    elif approved_sim is None:
        missing.append("승인 후보의 시뮬레이션 결과(simulation_results)가 없음")

    if missing or baseline_sim is None or approved_sim is None:
        return {
            "available": False,
            "amount": None,
            "baseline": _candidate_ref(baseline_candidate, baseline_sim),
            "approved": _candidate_ref(approved_candidate, approved_sim),
            "reason": " / ".join(missing) if missing else "알 수 없는 사유로 계산 불가",
        }

    if baseline_sim.expected_loss is None or approved_sim.expected_loss is None:
        return {
            "available": False,
            "amount": None,
            "baseline": _candidate_ref(baseline_candidate, baseline_sim),
            "approved": _candidate_ref(approved_candidate, approved_sim),
            "reason": "baseline 또는 승인 후보의 시뮬레이션 결과에 expected_loss 값이 없음",
        }

    amount = float(baseline_sim.expected_loss) - float(approved_sim.expected_loss)
    return {
        "available": True,
        "amount": amount,
        "baseline": _candidate_ref(baseline_candidate, baseline_sim),
        "approved": _candidate_ref(approved_candidate, approved_sim),
        "reason": None,
        "note": (
            "예상 회피손실 = baseline 후보의 기대손실(최초 시뮬레이션 결과로 고정 -- 사후에 유리하게 "
            "재계산하지 않음) - 승인된 후보의 기대손실(최신 시뮬레이션 결과). 실측 손실 데이터가 없어 "
            "실제 회피손실이 아니라 추정치입니다."
        ),
    }


# ------------------------------------------------------------------
# 비용 귀속 3분류
# ------------------------------------------------------------------


def classify_cost_attribution(
    db: Session, incident_id: int, embed_fn: EmbedFn | None = None
) -> dict[str, Any]:
    """GET /incidents/{id}/cost-attribution의 서비스 로직."""

    incident = IncidentRepository(db).get(incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"incident {incident_id} not found")

    avoided = compute_expected_avoided_loss(db, incident_id)
    amount = avoided["amount"]

    query_text = f"{incident.type} 사건({incident.location}) 관련 지연배상금(LD)·체선체화료(D&D) 귀책 조항"
    rag_unavailable = False
    try:
        chunks = search_similar_chunks(db, query_text, doc_types=["계약"], top_k=5, embed_fn=embed_fn)
    except GeminiAPIError:
        # 병합 전 리뷰에서 발견: GEMINI_API_KEY가 없는 환경(이 샌드박스 포함)에서는
        # 임베딩 호출 자체가 GeminiAPIError를 던져 이 엔드포인트 전체가 500으로
        # 죽었다. "계약 조항을 검색했지만 못 찾음"과 "애초에 검색할 수 없었음"은
        # 이 모듈 입장에서 같은 결론(귀책을 확정할 근거 없음 -> 안전한 기본값)으로
        # 이어져야 하므로, 검색 자체가 불가능한 경우도 "조항 0건"과 동일하게 처리한다.
        chunks = []
        rag_unavailable = True

    ld_hits = [c for c in chunks if _matches_any(c["chunk_text"], LD_KEYWORDS)]
    dnd_hits = [c for c in chunks if _matches_any(c["chunk_text"], DND_KEYWORDS)]

    if amount is None:
        breakdown = {DIRECT_PL_KEY: None, CUSTOMER_AVOIDANCE_KEY: None, DISPUTE_NEGOTIABLE_KEY: None}
        classification_note = (
            "예상 회피손실 금액을 산출할 수 없어(baseline 또는 승인 후보 시뮬레이션 결과 부재) "
            "금액 배분은 표시하지 않습니다. 분류 로직/근거만 아래에 참고 정보로 제공합니다."
        )
    elif dnd_hits and not ld_hits:
        breakdown = {DIRECT_PL_KEY: 0.0, CUSTOMER_AVOIDANCE_KEY: amount, DISPUTE_NEGOTIABLE_KEY: 0.0}
        classification_note = (
            "계약 조항 검색 결과 D&D(체선·체화료) 관련 조항만 발견됨 -- 업무 명세 §9 원칙"
            "('D&D는 화주가 부담하는 경우가 많다')에 따라 전액을 고객 회피비용으로 분류했습니다. "
            "이는 실제 계약서 검토·귀책 판단을 대체하지 않는 휴리스틱 기본값이며, 법무 검토 후 "
            "재분류될 수 있습니다."
        )
    elif ld_hits:
        # LD 조항이 있든(단독) D&D와 함께 있든, LD의 귀책 주체(당사/화주/제3자)를
        # 판단할 근거가 이 시스템에 없으므로 항상 분쟁·협상 가능 금액으로 분류한다.
        breakdown = {DIRECT_PL_KEY: 0.0, CUSTOMER_AVOIDANCE_KEY: 0.0, DISPUTE_NEGOTIABLE_KEY: amount}
        classification_note = (
            "계약 조항 검색 결과 LD(지연배상금) 관련 조항이 발견됨 -- 그러나 'LD는 계약상 귀책 주체가 "
            "부담한다'는 원칙 자체가 귀책 주체(당사/화주/제3자)를 특정하지 않고, 이 시스템은 실제 지연의 "
            "귀책을 판단하는 로직/데이터가 없으므로 임의로 당사 부담(직접손익)으로 단정하지 않고 전액을 "
            "분쟁·협상 가능 금액으로 분류했습니다. 귀책 판단은 법무·계약 담당자의 검토가 필요합니다."
        )
    else:
        breakdown = {DIRECT_PL_KEY: 0.0, CUSTOMER_AVOIDANCE_KEY: 0.0, DISPUTE_NEGOTIABLE_KEY: amount}
        if rag_unavailable:
            classification_note = (
                "계약 조항을 검색하지 못했습니다(임베딩 API 미구성 -- GEMINI_API_KEY 없음). "
                "'조항을 찾지 못함'과 동일하게 취급해 안전한 기본값으로 전액을 분쟁·협상 가능 "
                "금액으로 분류했습니다. GEMINI_API_KEY 설정 후 다시 조회하면 실제 계약 조항 "
                "검색 결과가 반영됩니다."
            )
        else:
            classification_note = (
                "계약 조항 검색 결과에 LD/D&D 관련 조항을 찾지 못했습니다(계약 문서가 이 사건에 연결되지 "
                "않았거나, 관련 조항이 없음). 안전한 기본값으로 전액을 분쟁·협상 가능 금액으로 분류했습니다."
            )

    return {
        "incident_id": incident_id,
        "is_heuristic": True,
        "rag_unavailable": rag_unavailable,
        "heuristic_disclaimer": (
            "이 분류는 실제 법무 판단이 아니라 계약 조항 검색 결과에 기반한 참고용 추정치입니다. "
            "최종 귀책·비용 부담 판단은 법무·계약 담당자의 검토를 거쳐야 합니다."
        ),
        "avoided_loss_basis": avoided,
        "matched_ld_clauses": [
            {
                "chunk_id": c["chunk_id"],
                "document_id": c["document_id"],
                "title": c["title"],
                "chunk_text": c["chunk_text"],
            }
            for c in ld_hits
        ],
        "matched_dnd_clauses": [
            {
                "chunk_id": c["chunk_id"],
                "document_id": c["document_id"],
                "title": c["title"],
                "chunk_text": c["chunk_text"],
            }
            for c in dnd_hits
        ],
        "breakdown": breakdown,
        "classification_note": classification_note,
    }
