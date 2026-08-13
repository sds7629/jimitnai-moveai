"""RAG 문서/청크 시드 스크립트 (agents/knowledge-retrieval.md).

적체/파업/관세 3개 시나리오에 대응하는 최소 문서 샘플(과거 사고 1건, SOP 1건,
플레이북 1건, 계약 2건 — 신구 버전을 함께 둬 유효기간 필터를 실제로 검증할
수 있게 한다)을 문서 유형별 청커(app.rag.chunking)로 청킹하고, Gemini
Embedding API로 임베딩한 뒤 documents / document_chunks 테이블에 적재한다.

RAG 문서 적재는 업로드 API가 아니라 이 스크립트로만 한다
(ARCHITECTURE.md §7.1 각주 / agents/knowledge-retrieval.md 담당 범위).

사용법:
    docker compose exec backend python -m app.scripts.seed_documents

GEMINI_API_KEY가 설정되어 있지 않으면 첫 임베딩 호출에서 `GeminiAPIError`가
발생하며, 아래 __main__ 블록이 이를 잡아 무엇을 설정해야 하는지 안내 메시지와
함께 non-zero exit code로 종료한다.

테스트(backend/tests/test_knowledge_retrieval.py)에서는 `run_seed(db,
embed_fn=<fake>)`에 네트워크를 타지 않는 fake 임베딩 함수를 주입해서, 실제
API 키 없이도 "문서 유형별로 다르게 청킹되어 저장되는지"를 검증한다.

재실행해도 안전하다: 문서 제목이 이미 존재하면 해당 문서는 건너뛴다(멱등).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.llm.gemini_api import GeminiAPIError
from app.llm.gemini_embeddings import embed_text
from app.models.document import Document
from app.rag.chunking import CHUNKERS
from app.repositories.documents import DocumentChunkRepository, DocumentRepository


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


@dataclass
class SeedDocument:
    doc_type: str
    title: str
    source: str
    raw_text: str
    valid_from: datetime | None = None
    valid_until: datetime | None = None


INCIDENT_TEXT = """\
사건 1: 태풍으로 인한 부산항 하역 중단 (2023년 9월)
원인: 제11호 태풍 영향으로 부산항 전 부두 하역 작업이 72시간 전면 중단되었다.
대응: 인접한 광양항으로 컨테이너 우회 반출 경로를 확보하고, 긴급 육상운송 계약을 체결해 부품 조달을 유지했다.
결과: 생산라인은 12시간 감산 운영 후 정상화되었고, 태풍 통과 48시간 내 정체 물량을 해소했다.

사건 2: 항만 노동조합 파업으로 인한 부품 재고 소진 (2022년 11월)
원인: 임금 협상 결렬로 항만 노동조합이 5일간 전면 파업에 돌입해 하역·통관 업무가 전면 중단되었다.
대응: 대체항(인천항)으로 신규 입고 물량을 우회시키고, 긴급 항공운송으로 핵심 부품(배터리)을 우선 조달했다.
결과: 파업 3일차에 배터리 재고가 안전재고 이하로 떨어졌으나 항공운송분으로 생산라인 정지를 회피했다. 파업 종료 후 정상 물량 흐름 회복까지 2일이 추가로 소요되었다.

사건 3: 관세 규정 변경으로 인한 통관 지연 (2024년 3월)
원인: 관세청이 특정 품목(반도체 부품)에 대한 원산지 증명서 제출 규정을 사전 공지 없이 강화했다.
대응: 통관 대행사와 협력해 누락된 서류를 48시간 내 긴급 보완했고, 향후 유사 규정 변경에 대비해 서류 사전 준비 체크리스트를 신설했다.
결과: 통관 지연은 발생했으나 사전 확보한 안전재고 덕분에 생산 영향은 감산 없이 흡수되었다.
"""

SOP_TEXT = """\
1단계: 사건 감지 및 1차 분류
사건 발생 보고를 접수하면 위기대응 담당자는 30분 이내에 사건 유형(적체/파업/관세/기타)을 분류하고 중복·오탐 여부를 확인한다.

2단계: 운영 스냅샷 확보
운영관리팀은 재고·생산·운송 현황 스냅샷을 확보하고 freshness/coverage를 기록한다. 최소 데이터 확보가 어려우면 제한 모드로 전환하고 가정을 명시한다.

3단계: 영향 경로 분석 및 대응안 후보 생성
Impact DAG를 기준으로 영향 전파 경로를 정리하고, 단일/복합 대응안 후보를 최소 2개 이상 도출한다.

4단계: 제약 검증 및 시뮬레이션
자원·비용·계약상 제약을 검증하고, 통과한 후보에 대해서만 손실 시뮬레이션을 수행한다.

5단계: 의사결정 패키지 작성 및 승인 요청
기대손실/P90/CVaR과 근거(FACT/INFERENCE/ASSUMPTION)를 포함한 의사결정 패키지를 작성해 담당자 승인을 요청한다.

6단계: SOP 배포 및 실행 추적
승인된 대응안에 대해 역할별 SOP를 사내 메신저로 배포하고, 수신·수락·완료 상태를 추적한다.
"""

PLAYBOOK_TEXT = """\
패턴 1: 대체항 우회 반출
적용 상황: 특정 항만의 하역·반출이 지연되거나 전면 중단된 경우 (적체, 파업 모두 해당).
조치: 인접 대체항의 여유 슬롯을 확인하고, 우선순위가 높은 컨테이너부터 우회 반출 경로로 전환한다. 대체항 통관 요건 사전 확인이 선행되어야 한다.

패턴 2: 긴급 대체운송 확보
적용 상황: 안전재고 소진까지 남은 시간이 정상 조달 리드타임보다 짧은 경우.
조치: 항공 또는 육상 긴급운송 수단을 확보해 핵심 부품만 우선 조달한다. 비용이 평시 대비 크게 상승하므로 사전 예산 승인 절차를 함께 진행한다.

패턴 3: 통관 서류 사전 확보
적용 상황: 관세·통관 규정 변경으로 추가 서류 요구가 발생하거나 예상되는 경우.
조치: 통관 대행사와 협력해 요구 서류 목록을 즉시 확인하고, 대체 통관경로(타 세관) 가용성을 함께 검토한다. 규정 변경 이력을 체크리스트로 남겨 재발에 대비한다.
"""

CONTRACT_TEXT_V1 = """\
제1조(목적) 본 계약은 화주와 운송사 간 컨테이너 해상운송 조건을 정함을 목적으로 한다.
제2조(지연배상) 운송사의 귀책사유로 하역이 72시간을 초과하여 지연되는 경우, 운송사는 화주에게 1일당 계약금액의 0.5%를 지연배상금으로 지급한다.
제3조(불가항력) 천재지변, 파업 등 불가항력 사유로 인한 지연에 대해서는 운송사에게 배상 책임을 묻지 않는다.
"""

CONTRACT_TEXT_V2 = """\
제1조(목적) 본 계약은 화주와 운송사 간 컨테이너 해상운송 조건을 정함을 목적으로 한다.
제2조(지연배상) 운송사의 귀책사유로 하역이 48시간을 초과하여 지연되는 경우, 운송사는 화주에게 1일당 계약금액의 0.8%를 지연배상금으로 지급한다.
제3조(불가항력) 천재지변, 파업 등 불가항력 사유로 인한 지연에 대해서는 운송사에게 배상 책임을 묻지 않되, 파업의 경우 사전 통지 의무를 이행해야 면책된다.
제4조(대체운송) 지연이 예상될 경우 운송사는 화주와 협의하여 대체 운송경로를 우선 제공해야 한다.
"""


SEED_DOCUMENTS: list[SeedDocument] = [
    SeedDocument(
        doc_type="사고",
        title="과거 공급망 위기 사고 리포트 (적체/파업/관세)",
        source="사내 위기대응팀 사고 아카이브",
        raw_text=INCIDENT_TEXT,
    ),
    SeedDocument(
        doc_type="SOP",
        title="공급망 위기 대응 SOP",
        source="위기대응팀 표준운영절차 v2",
        raw_text=SOP_TEXT,
        valid_from=_dt(2024, 1, 1),
        valid_until=None,
    ),
    SeedDocument(
        doc_type="플레이북",
        title="공급망 위기 대응 플레이북",
        source="위기대응팀 플레이북 v1",
        raw_text=PLAYBOOK_TEXT,
    ),
    SeedDocument(
        doc_type="계약",
        title="해상운송 계약서 (구버전, 만료)",
        source="해상운송사 계약 v1",
        raw_text=CONTRACT_TEXT_V1,
        valid_from=_dt(2021, 1, 1),
        valid_until=_dt(2023, 12, 31),
    ),
    SeedDocument(
        doc_type="계약",
        title="해상운송 계약서 (현행)",
        source="해상운송사 계약 v2",
        raw_text=CONTRACT_TEXT_V2,
        valid_from=_dt(2024, 1, 1),
        valid_until=None,
    ),
]


def run_seed(db: Session, embed_fn: Callable[[str], list[float]] | None = None) -> dict:
    """실제 적재 로직. `embed_fn`을 주입하면 Gemini API를 호출하지 않는다
    (테스트 전용 경로) — 기본값은 실제 `embed_text`."""
    embed = embed_fn or embed_text
    doc_repo = DocumentRepository(db)
    chunk_repo = DocumentChunkRepository(db)

    summary = {"documents_created": 0, "documents_skipped": 0, "chunks_created": 0}

    for seed_doc in SEED_DOCUMENTS:
        existing = db.query(Document).filter(Document.title == seed_doc.title).one_or_none()
        if existing is not None:
            summary["documents_skipped"] += 1
            continue

        chunker = CHUNKERS[seed_doc.doc_type]
        chunks = chunker(seed_doc.raw_text)
        if not chunks:
            raise ValueError(f"'{seed_doc.title}' 청킹 결과가 비어 있습니다.")

        # Embed every chunk *before* inserting the Document row. Each
        # repository .add() commits immediately (see AppendOnlyRepository),
        # so if we inserted the Document first and then hit a GeminiAPIError
        # partway through its chunks (e.g. GEMINI_API_KEY missing/revoked),
        # we'd be left with an orphan Document that has zero chunks -- and
        # the title-based idempotency check above would then treat it as
        # "already fully seeded" on every future retry, silently skipping it
        # forever. Embedding first makes each document all-or-nothing.
        embedded_chunks = [(chunk, embed(chunk.chunk_text)) for chunk in chunks]

        document = doc_repo.add(
            doc_type=seed_doc.doc_type,
            title=seed_doc.title,
            source=seed_doc.source,
            valid_from=seed_doc.valid_from,
            valid_until=seed_doc.valid_until,
        )
        summary["documents_created"] += 1

        for chunk, embedding in embedded_chunks:
            chunk_repo.add(
                document_id=document.id,
                chunk_text=chunk.chunk_text,
                chunk_type=chunk.chunk_type,
                embedding=embedding,
                metadata_=chunk.metadata,
            )
            summary["chunks_created"] += 1

    return summary


def main() -> None:
    db = SessionLocal()
    try:
        summary = run_seed(db)
    finally:
        db.close()
    print(
        f"[seed_documents] 문서 {summary['documents_created']}건 생성, "
        f"{summary['documents_skipped']}건 스킵(이미 존재), "
        f"청크 {summary['chunks_created']}건 생성"
    )


if __name__ == "__main__":
    try:
        main()
    except GeminiAPIError as exc:
        print(f"[seed_documents] 임베딩 생성 실패: {exc}", file=sys.stderr)
        print(
            "GEMINI_API_KEY 환경변수(.env 또는 docker-compose 환경변수)를 설정한 뒤 "
            "`docker compose exec backend python -m app.scripts.seed_documents`를 "
            "다시 실행하세요.",
            file=sys.stderr,
        )
        sys.exit(1)
