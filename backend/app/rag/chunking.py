"""문서 유형별 청킹 전략 (agents/knowledge-retrieval.md, ARCHITECTURE.md §3).

지식 검색 에이전트의 핵심 설계 원칙: "하나의 범용 청커로 통일하지 않는다."
문서 유형마다 원래 맥락 단위가 다르기 때문에 4개의 독립된 함수로 나눈다.

  - 계약   -> chunk_contract : 조항(제N조) 단위
  - SOP    -> chunk_sop      : 절차(N단계) 단위
  - 사고   -> chunk_incident : 사건 단위 (원인 -> 대응 -> 결과를 하나의 청크로)
  - 플레이북 -> chunk_playbook : 대응 패턴 단위

각 함수는 원문 텍스트(str)를 받아 `Chunk`(chunk_text, chunk_type, metadata) 목록을
반환한다. `metadata`는 document_chunks.metadata(JSONB)에 그대로 저장되어, 검색
결과를 프롬프트에 삽입할 때 조항 번호/단계 번호/사건 제목 등 구조적 정보를 함께
넘길 수 있게 한다.

입력 텍스트에 해당 유형의 구조적 마커(예: "제1조", "1단계")가 전혀 없는 경우,
각 함수는 예외를 던지지 않고 문서 전체를 단일 청크로 다루는 것으로 폴백한다 —
청킹 실패로 시드 스크립트 전체가 멎는 것보다, 못 나눈 문서라도 검색 대상에는
들어가는 편이 낫다는 판단이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    chunk_text: str
    chunk_type: str
    metadata: dict = field(default_factory=dict)


def _split_keep_none_empty(pattern: "re.Pattern[str]", text: str) -> list[str]:
    return [p.strip() for p in pattern.split(text) if p and p.strip()]


# ============================================================
# 계약 -> 조항 단위
# ============================================================
_CLAUSE_SPLIT = re.compile(r"(?=제\s*\d+\s*조)")
_CLAUSE_HEADER = re.compile(r"^제\s*(\d+)\s*조\s*(?:\(([^)]*)\))?")


def chunk_contract(text: str) -> list[Chunk]:
    """계약 문서를 "제N조(...)" 조항 단위로 청킹한다.

    조항 헤더가 없는 전문(前文, 당사자 소개 등)은 별도 조항 청크로 만들지
    않는다 — 근거로 인용될 단위가 아니기 때문이다. 조항 마커가 전혀 없으면
    문서 전체를 단일 "조항" 청크로 폴백한다.
    """
    if not text or not text.strip():
        return []

    parts = _split_keep_none_empty(_CLAUSE_SPLIT, text)
    chunks: list[Chunk] = []
    for part in parts:
        m = _CLAUSE_HEADER.match(part)
        if not m:
            continue
        metadata: dict = {"clause_no": f"제{m.group(1)}조"}
        if m.group(2):
            metadata["clause_title"] = m.group(2).strip()
        chunks.append(Chunk(chunk_text=part, chunk_type="조항", metadata=metadata))

    if not chunks:
        chunks.append(Chunk(chunk_text=text.strip(), chunk_type="조항", metadata={}))
    return chunks


# ============================================================
# SOP -> 절차 단위
# ============================================================
_STEP_SPLIT = re.compile(r"(?=\d+\s*단계)")
_STEP_HEADER = re.compile(r"^(\d+)\s*단계\s*[:：]?\s*(.*)")


def chunk_sop(text: str) -> list[Chunk]:
    """SOP 문서를 "N단계: ..." 절차 단위로 청킹한다."""
    if not text or not text.strip():
        return []

    parts = _split_keep_none_empty(_STEP_SPLIT, text)
    chunks: list[Chunk] = []
    for part in parts:
        m = _STEP_HEADER.match(part)
        if not m:
            continue
        metadata: dict = {"step_no": int(m.group(1))}
        title = m.group(2).splitlines()[0].strip() if m.group(2) else ""
        if title:
            metadata["step_title"] = title
        chunks.append(Chunk(chunk_text=part, chunk_type="절차", metadata=metadata))

    if not chunks:
        chunks.append(Chunk(chunk_text=text.strip(), chunk_type="절차", metadata={}))
    return chunks


# ============================================================
# 과거 사고 -> 사건 단위 (원인 -> 대응 -> 결과를 하나의 청크로)
# ============================================================
_CASE_SPLIT = re.compile(r"(?=사건\s*\d*\s*[:：])")
_CASE_HEADER = re.compile(r"^사건\s*(\d*)\s*[:：]\s*(.*)")
_CASE_FIELDS = re.compile(
    r"원인\s*[:：]\s*(.*?)\s*대응\s*[:：]\s*(.*?)\s*결과\s*[:：]\s*(.*)", re.DOTALL
)


def chunk_incident(text: str) -> list[Chunk]:
    """과거 사고 리포트를 "사건 단위"로 청킹한다.

    설계 원칙(agents/knowledge-retrieval.md): 원인 -> 대응 -> 결과를 별도
    청크로 쪼개지 않고 하나의 청크에 담아야 판단 맥락이 깨지지 않는다. 이
    함수는 "사건 N: 제목" 헤더로 사건 블록을 나눈 뒤, 블록 전체(원인/대응/
    결과 포함)를 chunk_text로 유지하면서 각 필드를 metadata로도 구조화해
    둔다.
    """
    if not text or not text.strip():
        return []

    parts = _split_keep_none_empty(_CASE_SPLIT, text)
    chunks: list[Chunk] = []
    for part in parts:
        header = _CASE_HEADER.match(part)
        fields = _CASE_FIELDS.search(part)
        metadata: dict = {}
        if header:
            if header.group(1):
                metadata["case_no"] = int(header.group(1))
            title = header.group(2).splitlines()[0].strip() if header.group(2) else ""
            if title:
                metadata["title"] = title
        if fields:
            metadata["cause"] = fields.group(1).strip()
            metadata["response"] = fields.group(2).strip()
            metadata["result"] = fields.group(3).strip()
        chunks.append(Chunk(chunk_text=part, chunk_type="사건", metadata=metadata))

    if not chunks:
        chunks.append(Chunk(chunk_text=text.strip(), chunk_type="사건", metadata={}))
    return chunks


# ============================================================
# 플레이북 -> 대응 패턴 단위
# ============================================================
_PATTERN_SPLIT = re.compile(r"(?=패턴\s*[0-9A-Za-z]*\s*[:：])")
_PATTERN_HEADER = re.compile(r"^패턴\s*([0-9A-Za-z]*)\s*[:：]\s*(.*)")


def chunk_playbook(text: str) -> list[Chunk]:
    """플레이북 문서를 "패턴 N: ..." 대응 패턴 단위로 청킹한다."""
    if not text or not text.strip():
        return []

    parts = _split_keep_none_empty(_PATTERN_SPLIT, text)
    chunks: list[Chunk] = []
    for part in parts:
        m = _PATTERN_HEADER.match(part)
        metadata: dict = {}
        if m:
            if m.group(1):
                metadata["pattern_id"] = m.group(1)
            title = m.group(2).splitlines()[0].strip() if m.group(2) else ""
            if title:
                metadata["pattern_title"] = title
        chunks.append(Chunk(chunk_text=part, chunk_type="대응패턴", metadata=metadata))

    if not chunks:
        chunks.append(Chunk(chunk_text=text.strip(), chunk_type="대응패턴", metadata={}))
    return chunks


# documents.doc_type 값 -> 청커 함수 매핑. 시드 스크립트 등에서 doc_type만
# 알고 있을 때 배선(wiring)하기 위한 조회 테이블일 뿐이며, 청킹 로직 자체는
# 여전히 위 4개의 분리된 함수가 각각 담당한다 (범용 청커로의 통합이 아니다).
CHUNKERS = {
    "계약": chunk_contract,
    "SOP": chunk_sop,
    "사고": chunk_incident,
    "플레이북": chunk_playbook,
}
