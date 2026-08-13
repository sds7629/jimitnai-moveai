# 기술 아키텍처 확정안 (MVP)

`simulation-supply-chain-tool.md`의 업무 명세를 실제로 구현하기 위해 확정한 기술 결정을 정리한다. 이 문서는 업무 명세가 아니라 구현 스코프와 데이터 구조를 다룬다.

## 1. 확정된 결정

1. 백엔드 프레임워크: **FastAPI**
2. 벡터 검색/RAG 저장소: **PostgreSQL + pgvector** (별도 벡터 DB 없이 단일 RDB로 운영 데이터와 임베딩을 함께 관리)
3. 향후 피해 예측 방식: **LLM 기반 추정**. 별도의 수치 시뮬레이션(몬테카를로 등) 엔진을 만들지 않고, 다음 세 가지를 프롬프트로 결합해 LLM이 기대손실·P90·CVaR·핵심 민감도 변수를 직접 산출한다.
   - Impact DAG 경로 (영향 전파 경로와 각 노드의 계산 근거)
   - RAG 검색 결과 (과거 유사 사고, SOP, 계약, 플레이북)
   - 현재 운영 스냅샷 (재고·생산·운송 상태 — 시드 데이터 기반)
4. 외부 시스템 실시간 연동은 이번 스코프에서 제외한다. 항만·통관·ETA·재고·생산 데이터는 실제 연동 대신 **시나리오 흐름을 따르는 시드 데이터**로 대체한다.
5. 시드 데이터는 3개 시나리오를 대응한다: **항만 적체 / 파업 / 관세**.
6. 모든 인프라는 **Docker Compose**로 구성한다. 로컬 개발·데모 환경에서 별도 설치 없이 `docker compose up` 한 번으로 DB(pgvector)와 백엔드가 뜨는 것을 기준으로 한다.

## 2. 데이터 계층 (Postgres + pgvector)

| 테이블 | 용도 | 비고 |
|---|---|---|
| `incidents` | 사건 정의, 상태, 유형, 발생시각 | 중복·오탐 판정 이력 포함 |
| `operational_snapshots` | 사건ID + 데이터 버전 + 시나리오 버전 + 가정 목록 | append-only, 버전 고정 |
| `impact_dag_nodes` / `impact_dag_edges` | Impact DAG 노드·엣지 | 스냅샷 버전에 귀속 |
| `response_candidates` | 대응안 후보, 실행 가능성·제약 검증 결과 | 제외 사유 포함 |
| `simulation_results` | LLM이 산출한 예측 결과 | 기대손실/P90/CVaR/민감도/근거를 JSONB로 저장 |
| `decision_packages` | 대응안별 의사결정 근거 묶음 | FACT/INFERENCE/ASSUMPTION 태깅 |
| `approvals` | 승인/반려/조건부승인/에스컬레이션 이력 | |
| `audit_log` | 발송·수신·수락·완료·실패 등 전 이벤트 | append-only |
| `documents` / `document_chunks` | RAG 대상 원문과 청크 | `document_chunks`에 pgvector 임베딩 컬럼 |
| `seed_scenarios` | 시나리오별 초기 사건·스냅샷·DAG·대응안 시드 | 적체/파업/관세 3종 |

baseline 불변성 요구(회피손실 계산 기준) 때문에 `operational_snapshots`, `simulation_results`는 UPDATE 없이 새 버전을 추가하는 append-only 구조로 설계한다.

## 3. RAG 계층

- **문서 유형**: 과거 사고 리포트, SOP, 계약 조항, 플레이북 — `documents.doc_type`으로 구분
- **청킹 전략**: 문서 유형별로 다르게 적용
  - 계약: 조항 단위
  - SOP: 절차 단위
  - 과거 사고: 사건 단위 (원인 → 대응 → 결과를 하나의 청크로)
  - 플레이북: 대응 패턴 단위
- **임베딩**: Gemini Embedding API 사용 (기존 `llm/` 프로바이더 추상화와 동일한 인증 체계를 공유)
- **검색**: pgvector cosine similarity + `doc_type` 필터 + 유효기간 필터(계약/SOP의 최신 유효본만)

## 4. LLM 예측 파이프라인

1. Impact DAG에서 현재 사건의 영향 전파 경로 추출
2. RAG로 유사 과거 사고·SOP·플레이북 검색 (문서 유형별로 top-k 검색 후 병합)
3. 현재 운영 스냅샷(재고·생산·운송 상태 — 시드 데이터 기반) 첨부
4. 위 세 가지를 결합한 프롬프트로 LLM 호출 → 기대손실·P90·CVaR·핵심 민감도 변수·신뢰도를 구조화된 JSON으로 응답받음
5. 응답 스키마에 FACT(스냅샷에서 직접 가져온 값) / INFERENCE(DAG 경로로 추론한 값) / ASSUMPTION(LLM이 명시한 가정)을 필드로 강제해 근거 구분을 스키마 레벨에서 보장

## 5. 시드 시나리오 3종

| 시나리오 | 트리거 | 영향 경로 |
|---|---|---|
| 항만 적체 | 항만 하역 지연 | 컨테이너 반출 지연 → 부품 재고 소진 → 생산라인 중단 → 완성차 출고 지연 → 딜러 납기 위반 |
| 파업 | 항만/운송 노동 파업 | 하역·통관 전면 중단 → 컨테이너 반출 불가 → 재고 소진 → 생산라인 중단 |
| 관세 | 관세·통관 규정 변경 | 통관 지연/추가 서류 요구 → 반출 지연 → 재고 소진 → 생산 영향 |

각 시나리오는 시드 데이터로 다음을 포함한다: 사건 정의, 초기 운영 스냅샷, Impact DAG, 최소 1개 이상의 대응안 후보. 세 시나리오 모두 동일한 스키마를 사용하므로 트리거 지점과 초기 노드만 다르고 이후 파이프라인(제약검증 → 시뮬레이션 → 의사결정 패키지)은 공통 로직으로 처리한다.

## 6. 이번 스코프에서 제외

- 실시간 외부 시스템 연동 (항만/통관/ETA/재고/생산 실시간 API) — 시드 데이터로 대체
- 사내 메신저 실제 연동 — 발송 로직은 로그/스텁으로 대체
- 스케줄러 기반 자동 에스컬레이션 — 기한 필드는 저장하되 실제 알림 발송은 이번 스코프 밖
- RBAC(역할 기반 접근 제어) — 승인자 식별은 단순 필드로 기록, 정교한 권한 체계는 이후 과제

---

## 7. 프론트엔드 / 백엔드 기능 분리

업무 흐름(2장) 단계별로 화면과 API를 1:1로 매핑한다. 백엔드는 워크플로 단계마다 하나의 API 그룹을 소유하고, 프론트엔드는 해당 그룹의 응답 스키마만 계약(contract)으로 받아 화면을 만든다 — 두 작업이 서로의 내부 구현을 몰라도 동시에 진행 가능하게 하는 것이 목적이다.

### 7.1 단계별 화면 ↔ API 매핑

| 워크플로 단계 | 프론트엔드 화면/기능 | 백엔드 API 그룹 |
|---|---|---|
| 사건 감지·입력 | 시드 시나리오 선택 화면(적체/파업/관세), 사건 목록·상태 뱃지 | `POST /incidents`, `GET /incidents`, 중복·오탐 검증 로직 |
| 운영 데이터·스냅샷 | 운영 현황 대시보드(재고·생산·운송 상태, freshness/coverage 표시) | `GET /incidents/{id}/snapshots/latest` |
| Impact DAG | DAG 그래프 시각화 컴포넌트 (노드 클릭 시 근거·불확실성 표시) | `GET /incidents/{id}/impact-dag` |
| 대응안 생성·제약검증·시뮬레이션 | 대응안 비교 카드/테이블, 손실분포(P90/CVaR) 차트, 제외 사유 표시 | `POST /incidents/{id}/simulate` (LLM 파이프라인 트리거, 비동기), `GET /incidents/{id}/candidates` |
| 의사결정 근거 | 근거 패널(FACT/INFERENCE/ASSUMPTION 뱃지, 신뢰도, 핵심 민감도 변수), 결정기한 카운트다운 | `GET /incidents/{id}/decision-package` |
| 담당자 승인 | 승인/조건부승인/반려/수정요청 버튼 + 사유 입력 폼 | `POST /incidents/{id}/approvals` |
| SOP 배포 | 역할별 SOP 미리보기, 발송·수신·수락·완료 상태 트래커 | `POST /approvals/{id}/dispatch-sop`, `GET /incidents/{id}/sop-status` |
| 실행 추적 | 타임라인 뷰, 편차·에스컬레이션 알림 배너 | `PATCH /sop/{sop_id}/status`, `GET /incidents/{id}/timeline` |
| 사후보고서 | 리포트 뷰어(읽기전용), 섹션별 표시(예상 vs 실제, 귀책, 개선사항) | `GET /incidents/{id}/post-report` |
| ROI·비용 귀속 | 절감액 구분 차트(직접손익 / 고객회피비용 / 분쟁가능금액), 연간 ROI 카드 | `GET /reports/roi`, `GET /incidents/{id}/cost-attribution` |

RAG 문서(과거 사고·SOP·계약·플레이북) 적재는 화면 없이 백엔드 시드 스크립트로만 처리한다 — §6에서 실시간 연동을 스코프 밖으로 뒀으므로 별도 업로드 UI는 만들지 않는다.

### 7.2 실시간 갱신 경계

동적 변수 변경이나 재시뮬레이션으로 의사결정 패키지가 갱신되면 프론트가 폴링하지 않고 서버가 밀어준다.

- `GET /incidents/{id}/stream` (SSE) — decision-package 갱신, DAG 갱신, SOP 상태 변경 이벤트를 push
- 프론트는 이 스트림 하나만 구독하고, 이벤트 타입에 따라 해당 화면 컴포넌트만 다시 fetch(`GET /incidents/{id}/decision-package` 등)하는 방식으로 단순화
- WebSocket 대신 SSE를 쓰는 이유: 이 시스템은 서버→클라이언트 단방향 push만 필요하고(클라이언트가 실시간으로 뭔가를 보내지 않음), FastAPI에서 구현이 더 단순함

### 7.3 병렬 작업을 위한 원칙

- **Contract-first**: 위 7.1 표의 API 그룹별 요청/응답 스키마(Pydantic 모델)를 백엔드가 먼저 확정해 OpenAPI로 공유한다. 프론트는 실제 LLM 파이프라인이 붙기 전에도 이 스키마 + 시드 시나리오 3종의 고정 응답(fixture)으로 화면을 완성할 수 있다.
- **시드 데이터가 곧 프론트 개발용 mock**: 적체/파업/관세 3개 시나리오는 백엔드가 만드는 즉시 프론트의 개발/데모 데이터로 그대로 재사용된다. 별도 mock 서버가 필요 없다.
- **경계선은 워크플로 단계**: 한 사람이 "시뮬레이션 로직"과 "시뮬레이션 결과 화면"을 동시에 맡지 않는다. API 그룹 단위로 담당을 나누면 백엔드 쪽 로직 변경이 프론트 작업을 막지 않는다(응답 스키마만 안 바뀌면 됨).
- **DAG 시각화는 별도 트랙**: 그래프 렌더링(예: React Flow, d3)은 다른 화면과 의존성이 적어 가장 먼저 독립적으로 착수 가능 — 고정된 mock DAG JSON으로 바로 시작할 수 있다.

---

## 8. 인프라 구성 (Docker Compose)

로컬 개발과 데모 환경을 `docker compose up` 한 번으로 재현 가능하게 구성한다. 각자 로컬에 Postgres/pgvector를 따로 설치하지 않는다. 이 장은 아직 실제 코드/설정 파일을 만들기 전 단계의 청사진이며, 실제 스캐폴딩 작업은 별도로 진행한다.

### 8.1 서비스 구성

| 서비스 | 이미지/빌드 | 역할 |
|---|---|---|
| `db` | `pgvector/pgvector:pg16` | 운영 데이터 + RAG 임베딩을 함께 저장. 초기화 스크립트로 `CREATE EXTENSION vector` 자동 실행 |
| `backend` | `./backend` (Dockerfile) | FastAPI 앱. `db`의 healthcheck 통과 후 기동, `.env`로 DB 접속정보·LLM 프로바이더 설정 주입 |
| `frontend` | `./frontend` (Dockerfile) | React + Vite 개발 서버. 7.1의 화면들을 서빙하고 `backend` API를 호출 |
| `adminer` | `adminer` | DB 내용을 브라우저에서 바로 확인 (해커톤 디버깅용, 선택적) |

프론트엔드도 `db`·`backend`와 함께 `docker compose up` 한 번으로 뜨도록 편입한다 — 별도 dev 서버를 각자 로컬에서 따로 띄우지 않는다.

### 8.2 디렉토리 구조(예정)

```text
jimitnai-moveai/
├── docker-compose.yml
├── .env.example
├── db/
│   └── init/
│       ├── 001-init-extensions.sql   # CREATE EXTENSION vector
│       └── 002-seed-scenarios.sql (또는 py 스크립트)  # 적체/파업/관세 시드 적재
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py           # FastAPI 앱 진입점, /health 등
│   │   ├── core/
│   │   │   └── config.py     # 환경변수 기반 설정(pydantic-settings)
│   │   ├── db.py             # SQLAlchemy 엔진/세션
│   │   ├── llm/              # 기존 feature/llm-provider 작업 병합 위치
│   │   └── ...               # 이후 모델/라우터/RAG/에이전트 모듈 추가
│   └── tests/
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx
        ├── api/               # 백엔드 API 클라이언트 (7.1 표의 API 그룹과 매칭)
        ├── pages/             # 7.1 표의 화면 단위와 1:1 매칭
        └── components/
            └── dag/           # Impact DAG 시각화 (React Flow 등)
```

`llm/` 프로바이더 모듈(Gemini API ↔ 로컬 `claude -p` 스위칭)은 별도 브랜치(`feature/llm-provider`)에서 이미 작업 중이며, 백엔드 스캐폴딩 시 `backend/app/llm/`로 병합해 들어간다.

### 8.3 환경변수

| 변수 | 예시 값 | 용도 |
|---|---|---|
| `POSTGRES_DB` | `moveai` | DB 이름 |
| `POSTGRES_USER` | `moveai` | DB 사용자 |
| `POSTGRES_PASSWORD` | `moveai` | DB 비밀번호 (로컬 기본값, 운영 배포 시 교체 필요) |
| `DATABASE_URL` | `postgresql+psycopg://moveai:moveai@db:5432/moveai` | 백엔드가 `db` 서비스에 접속하는 전체 URL |
| `APP_ENV` | `local` \| `docker` | 실행 환경 구분 |
| `LLM_PROVIDER` | `gemini_api` \| `claude_cli` | `feature/llm-provider`에서 정의한 LLM 백엔드 선택 |
| `GEMINI_API_KEY` | (비움) | Gemini API 키 |
| `GEMINI_MODEL` | `gemini-2.0-flash` | 사용할 Gemini 모델 |
| `VITE_API_BASE_URL` | `http://localhost:8000` | 프론트엔드(브라우저)가 호출할 백엔드 주소 |

비밀값(`GEMINI_API_KEY` 등)은 이미지나 compose 파일에 하드코딩하지 않고 `.env` 파일(커밋 제외, `.env.example`만 커밋)로만 주입한다.

### 8.4 포트

| 서비스 | 포트 | 용도 |
|---|---|---|
| `db` | 5432 | Postgres 접속 (로컬 클라이언트로 직접 붙어 디버깅할 때) |
| `backend` | 8000 | FastAPI (Swagger UI: `/docs`) |
| `frontend` | 5173 | Vite 개발 서버 |
| `adminer` | 8080 | DB 웹 UI |

### 8.5 운영 원칙

- 백엔드 컨테이너는 개발 중 코드 변경이 바로 반영되도록 소스 디렉토리를 볼륨 마운트하고 `--reload`로 띄운다.
- 프론트엔드 컨테이너도 소스 디렉토리를 볼륨 마운트해 Vite HMR(Hot Module Replacement)이 그대로 동작하게 하되, `node_modules`는 컨테이너 내부 설치본을 유지하도록 별도(익명) 볼륨으로 분리한다.
- `frontend`는 브라우저(호스트)에서 직접 `backend`를 호출하므로 두 서비스는 서로 다른 origin이다 — `backend`에 `frontend`의 origin(`http://localhost:5173`)을 허용하는 CORS 설정이 필요하다.
- DB 데이터는 named volume으로 영속화해 컨테이너 재시작 시에도 시드 데이터가 유지된다.
- 시드 데이터(적체/파업/관세 3종)는 컨테이너 최초 기동 시 자동으로 적재하는 초기화 스크립트로 관리해, 누구든 `docker compose up` 한 번으로 동일한 데모 상태를 재현할 수 있게 한다.
- `db` 서비스의 healthcheck가 통과해야 `backend`가 기동하도록, `backend`의 헬스체크(`/health`)가 통과해야 `frontend`가 기동하도록 `depends_on: condition: service_healthy`를 체이닝한다.
