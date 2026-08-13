# 프론트엔드 기술 아키텍처 확정안 (MVP)

`ARCHITECTURE.md`의 백엔드 결정과 `simulation-supply-chain-tool.md`의 업무 명세를 기준으로,
`ARCHITECTURE.md` §7(프론트엔드/백엔드 기능 분리)에서 정의한 화면↔API 매핑을 실제로 구현하기 위한
프론트엔드 기술 스택을 정리한다.

## 1. 확정된 결정

| 영역 | 선택 | 비고 |
|---|---|---|
| 프레임워크 | **Vite + React (SPA)** | 서버 컴포넌트 불필요, CSR + SSE 조합이 단순함 |
| 언어 | **TypeScript** | 백엔드 OpenAPI 스키마와 타입 동기화 전제 |
| 라우팅 | **React Router** | SPA이므로 클라이언트 라우팅 직접 구성 |
| 데이터 페칭 | **TanStack Query** | 서버 상태 캐싱·재검증, SSE 이벤트와 캐시 무효화 연동 |
| 타입/클라이언트 생성 | **openapi-typescript (+ openapi-fetch)** | 백엔드 OpenAPI 스펙에서 타입·클라이언트 자동 생성, Contract-first 유지 |
| UI 컴포넌트 | **Tailwind CSS + shadcn/ui** | 뱃지·카드·타임라인 등 도메인 특화 UI를 직접 조립 |
| 폼 | **react-hook-form + zod** | 승인/반려 사유 입력 등 폼 검증, zod 스키마는 OpenAPI 타입과 병행 유지 |
| 시각화(DAG) | **React Flow** | 노드 클릭 시 근거/불확실성 표시, 별도 트랙으로 독립 착수 가능 |
| 시각화(차트) | **Recharts** | 손실분포(P90/CVaR), ROI/비용귀속 차트 |
| 실시간 갱신 | **네이티브 EventSource + 커스텀 훅** | `GET /incidents/{id}/stream` 구독, 이벤트 타입별 TanStack Query invalidate |
| 개발용 목업 | **MSW (Mock Service Worker)** | 시드 시나리오 3종 fixture를 백엔드 전에 화면 완성용으로 재사용 |
| 테스트 | **Vitest + React Testing Library** | Vite 네이티브, 컴포넌트/훅 단위 테스트 |

## 2. 프레임워크가 SPA인 이유와 트레이드오프

- SSR/SEO 요구가 없는 내부 운영 도구이므로 Next.js의 서버 컴포넌트 이점이 크지 않음
- SSE 구독(§4)은 클라이언트 전용 로직이라 순수 CSR 쪽이 클라이언트/서버 경계 관리가 단순함
- 트레이드오프: 라우팅(React Router)과 배포(정적 호스팅)를 직접 구성해야 함 — 해커톤 규모에서는 설정 비용이 Next.js 대비 낮다고 판단

## 3. 라우팅 구조

`ARCHITECTURE.md` §7.1 표를 기준으로 사건(incident) 단위 중첩 라우팅을 구성한다.

```text
/                                   시드 시나리오 선택 화면 (적체/파업/관세), 사건 목록
/incidents/:id                      운영 현황 대시보드 (스냅샷 freshness/coverage)
/incidents/:id/dag                  Impact DAG 그래프 시각화
/incidents/:id/candidates           대응안 비교 카드/테이블, 손실분포 차트
/incidents/:id/decision-package     근거 패널 (FACT/INFERENCE/ASSUMPTION), 결정기한 카운트다운
/incidents/:id/approval             승인/조건부승인/반려/수정요청 폼
/incidents/:id/sop                  역할별 SOP 미리보기·상태 트래커
/incidents/:id/timeline             실행 추적 타임라인, 편차·에스컬레이션 배너
/incidents/:id/post-report          사후보고서 뷰어 (읽기전용)
/reports/roi                        연간 ROI, 절감액 구분 대시보드
```

`/incidents/:id`를 공통 레이아웃으로 두고 하위 라우트는 탭 형태로 전환 — 사건 컨텍스트(스냅샷 버전, 시나리오 버전)를
상위 레이아웃에서 한 번만 로드해 하위 화면에 전달한다.

## 4. 데이터 페칭 & 타입 동기화 파이프라인

1. 백엔드가 FastAPI에서 OpenAPI 스펙을 확정·배포
2. `openapi-typescript`로 타입 생성 → `openapi-fetch` 클라이언트에 타입 바인딩
3. TanStack Query 훅에서 생성된 클라이언트를 감싸서 사용 (`useIncidentQuery`, `useDecisionPackageQuery` 등)
4. CI에서 타입 생성 스크립트를 실행해 백엔드 스키마 변경 시 프론트 타입이 자동 갱신되도록 함 (수동 동기화 지점 제거)

### SSE 연동

- `useIncidentStream(incidentId)` 훅이 `EventSource`로 `/incidents/{id}/stream` 구독
- 이벤트 타입(`decision_package_updated`, `dag_updated`, `sop_status_changed`)에 따라 해당 리소스의
  TanStack Query 키만 `invalidateQueries`로 무효화 — 폴링 없이 필요한 화면만 재요청 (§7.2 원칙과 일치)

## 5. 상태 관리

- **서버 상태**: TanStack Query가 전담 (캐시, 재검증, SSE 무효화)
- **클라이언트 전용 UI 상태** (모달 열림, 필터 선택 등): 컴포넌트 로컬 `useState` + 필요한 경우 React Context
- 별도 전역 상태 라이브러리(Zustand 등)는 도입하지 않음 — 현재 명세상 컴포넌트 트리를 넘나드는 복잡한
  클라이언트 전용 상태가 식별되지 않음. 필요성이 확인되면 이 항목만 재검토

## 6. 개발용 목업 전략

- `ARCHITECTURE.md` §7.3: "시드 데이터가 곧 프론트 개발용 mock" 원칙을 MSW로 구현
- 적체/파업/관세 3개 시드 시나리오를 MSW 핸들러의 고정 응답으로 등록
- 백엔드 API가 준비되기 전에도 동일한 화면 코드로 목업/실제 서버를 스위칭 가능 (환경변수로 MSW 활성화 여부만 전환)
- 백엔드 시드 스크립트와 프론트 MSW fixture는 동일한 JSON을 참조해 이중 관리 방지 (예: `seed/` 디렉토리 공유 또는 백엔드가 시드 데이터를 정적 자산으로 export)

## 7. 폴더 구조 (초안)

```text
src/
  app/                 라우터 설정, 레이아웃
  pages/               라우트별 페이지 컴포넌트 (§3 매핑과 1:1)
  features/            도메인 단위 모듈 (incident, dag, candidates, decision-package, sop, timeline, report)
    <feature>/
      components/
      hooks/           useXxxQuery, useXxxMutation
      types.ts         (일부는 생성 타입 re-export)
  shared/
    api/               openapi-fetch 클라이언트, 생성된 타입
    ui/                 shadcn/ui 기반 공통 컴포넌트
    hooks/              useIncidentStream 등 공통 훅
  mocks/                MSW 핸들러 + 시드 시나리오 fixture
```

## 8. 이번 스코프에서 제외

- SSR/SEO 대응 (내부 도구이므로 불필요)
- 전역 상태 관리 라이브러리 (필요성 확인 전까지 보류)
- 인증/RBAC UI (`ARCHITECTURE.md` §6과 동일하게 이번 스코프 제외, 승인자 식별은 단순 필드로만 표시)
- 다국어(i18n) 대응
