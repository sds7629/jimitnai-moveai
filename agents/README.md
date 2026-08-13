# agents/ 디렉토리 안내

이 디렉토리는 **백엔드 개발을 시작하기 전에** 참고하는 기능별 페르소나·작업 지침 모음이다.

- `simulation-supply-chain-tool.md` §7.1의 "멀티에이전트 역할 구성" 표에 나온 11개 에이전트를 기준으로,
- `ARCHITECTURE.md`에서 확정한 실제 DB 테이블·API 엔드포인트·LLM 파이프라인 구조에 그 역할을 대응시켜
- "이 기능을 구현할 때 어떤 입장에서, 무엇을 소유하고, 무엇을 지켜야 하는가"를 한 페이지로 정리한 것이다.

업무 명세(`simulation-supply-chain-tool.md`)가 "왜/무엇을"을 정의하고, 아키텍처 확정안(`ARCHITECTURE.md`)이 "어떻게(기술적으로)"를 정의한다면, 이 디렉토리는 그 둘을 백엔드 구현 단위(API 그룹/모듈)로 잇는 다리 역할을 한다.

## 사용 방법

1. 백엔드에서 특정 API 그룹이나 모듈을 구현하기 전에, 해당하는 페르소나 문서를 먼저 읽는다.
2. 문서의 "담당 범위"로 이 모듈이 소유해야 할 테이블/엔드포인트/코드 경로를 확인한다.
3. "의존 관계"로 이 모듈이 어떤 모듈의 출력을 받고, 어떤 모듈에 무엇을 넘기는지 확인해 인터페이스(Pydantic 스키마)부터 확정한다 — `ARCHITECTURE.md` §7.3의 contract-first 원칙과 동일하다.
4. "작업 지침"과 "완료 기준"을 구현 체크리스트로 사용한다.
5. 실제 코드 작업은 `CLAUDE.md`의 worktree 워크플로(전용 브랜치 생성 → 구현 → 테스트 3케이스 이상 → 커밋 → 병합 → worktree 정리)를 그대로 따른다. 이 문서들은 그 워크플로에서 "무엇을 만들지"에 대한 참고 자료이며, 워크플로 자체를 대체하지 않는다.

## 페르소나 목록 (업무 흐름 순서)

| 순서 | 페르소나 문서 | 대응하는 업무 에이전트 (업무 명세 §7.1) | 담당 API 그룹 (ARCHITECTURE.md §7.1) |
|---|---|---|---|
| 1 | [incident-intake.md](./incident-intake.md) | 사건 해석 에이전트 | 사건 감지·입력 |
| 2 | [knowledge-retrieval.md](./knowledge-retrieval.md) | 지식 검색 에이전트 | (RAG 적재/검색 — 화면 없는 백엔드 전용) |
| 3 | [operational-graph.md](./operational-graph.md) | 운영 그래프 에이전트 | 운영 데이터·스냅샷, Impact DAG |
| 4 | [response-design.md](./response-design.md) | 대응 설계 에이전트 | 대응안 생성 (simulate 파이프라인 1단계) |
| 5 | [constraint-validation.md](./constraint-validation.md) | 제약 검증 에이전트 | 실행 가능성·제약 검증 (simulate 파이프라인 2단계) |
| 6 | [simulation.md](./simulation.md) | 시뮬레이션 에이전트 | 대응안 시뮬레이션 (simulate 파이프라인 3단계, LLM 예측) |
| 7 | [response-optimization.md](./response-optimization.md) | 대응 최적화 에이전트 | 의사결정 근거 (decision-package) |
| 8 | [communication-sop.md](./communication-sop.md) | 커뮤니케이션 에이전트 | SOP 배포 |
| 9 | [execution-tracking.md](./execution-tracking.md) | 실행 추적 에이전트 | 실행 추적 |
| 10 | [post-report.md](./post-report.md) | 사후보고 에이전트 | 사후보고서, ROI·비용 귀속 |
| 11 | [orchestration.md](./orchestration.md) | 오케스트레이션 에이전트 | 담당자 승인 분기, SSE 스트림, 재시뮬레이션 트리거 |
| 12 | [platform-infra.md](./platform-infra.md) | (업무 명세에 없는 지원 역할) | DB 스키마·시드 로더·Docker 인프라 |

11개는 업무 명세에 이미 이름이 있는 "의사결정/처리" 에이전트이고, 12번째(`platform-infra`)는 업무 로직이 아니라 그 위에서 돌아가는 데이터/인프라 기반을 소유하는 지원 역할이라 별도로 추가했다.

## 이 페르소나들이 실제 코드에서 "에이전트 프로세스"를 의미하지는 않는다

`ARCHITECTURE.md` §1-3에서 이미 결정한 대로, 이번 MVP는 각 역할을 별도의 자율 에이전트 런타임으로 구현하지 않는다. 대응 설계·제약 검증·시뮬레이션 세 역할은 `POST /incidents/{id}/simulate` 하나의 파이프라인 안에서 순차적으로 처리되는 단계이며, 시뮬레이션 자체도 몬테카를로 엔진이 아니라 LLM 1회 호출로 기대손실·P90·CVaR·민감도를 직접 산출한다. 여기서 "페르소나"는 그 역할이 참고해야 할 관점·제약·출력 형식을 뜻하며, FastAPI 코드에서는 각각 별도 함수/모듈/프롬프트 블록으로 구현된다.
