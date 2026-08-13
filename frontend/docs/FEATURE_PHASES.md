# 프론트엔드 기능 정의 및 페이즈 분리

`FRONTEND_ARCHITECTURE.md` §3 라우팅 표와 `simulation-supply-chain-tool.md` §2 업무 흐름을 기준으로
필요한 기능을 전부 나열하고, 백엔드 진행 속도에 맞춰 기능 하나씩 순서대로 진행한다.

## 원칙

- **기능 하나 = 페이즈 하나.** 한 페이즈 안에서 여러 화면을 동시에 벌리지 않는다.
- **백엔드가 이미 만든 API가 있는 기능부터.** 없는 기능은 목업을 유지한 채 뒤로 미룬다.
- **스키마는 무겁게 계약 협상하지 않고, 백엔드가 실제로 응답하는 필드에 맞춰 가볍게 realign한다.**
  백엔드 속도가 빠르므로 문서로 먼저 스펙을 고정하기보다 실제 Pydantic 스키마를 그때그때 확인해서 맞춘다.
- 각 페이즈는 "완료 조건"을 명시한다 — 완료 조건을 만족하면 다음 페이즈로 넘어간다.

## 전체 기능 목록과 현재 상태

`ARCHITECTURE.md` §7.1 표의 10개 워크플로 화면 기준. (2026-08-13 기준, `backend` 브랜치 병합 시점)

| # | 기능 | 백엔드 API | 상태 |
|---|---|---|---|
| 1 | 사건 목록 (시드 시나리오 선택) | `GET /incidents` | ✅ 있음 |
| 2 | Impact DAG 시각화 | `GET /incidents/{id}/impact-dag` | ✅ 있음 (스키마 재정렬 필요) |
| 3 | 운영 스냅샷 상태 (freshness/coverage) | `GET /incidents/{id}/snapshots/latest` | ✅ 있음 |
| 4 | 대응안 후보 비교·시뮬레이션 | `POST /incidents/{id}/simulate`, `GET .../candidates` | ❌ 없음 (DB 모델·리포지토리만 존재) |
| 5 | 의사결정 근거 패널 | `GET /incidents/{id}/decision-package` | ❌ 없음 |
| 6 | 담당자 승인 | `POST /incidents/{id}/approvals` | ❌ 없음 |
| 7 | SOP 배포·미리보기 | `POST /approvals/{id}/dispatch-sop`, `GET .../sop-status` | ❌ 없음 |
| 8 | 실행 추적 타임라인 | `GET /incidents/{id}/timeline` | ❌ 없음 (`audit_log` 테이블은 있음) |
| 9 | 사후보고서 | `GET /incidents/{id}/post-report` | ❌ 없음 |
| 10 | ROI·비용 귀속 | `GET /reports/roi`, `GET .../cost-attribution` | ❌ 없음 |

지금 실연동 가능한 건 1~3번뿐이다. 4번부터는 백엔드에 해당 라우터가 생기는 시점에 맞춰 순서대로 착수한다.

---

## Phase 1 — 사건 목록 (진입 화면)

- **백엔드**: `GET /incidents` — 완성 (`IncidentListItem`: id/type/location/occurred_at/status/duplicate_of_incident_id/created_at)
- **확인된 사실**: DB가 컨테이너 최초 기동 시 적체/파업/관세 3개 사건을 이미 시드로 넣어두므로, 별도
  "사건 생성 폼" 없이 `GET /incidents` 호출만으로 3개 시드 시나리오가 바로 내려온다.
- **범위**:
  - `react-router` 최소 도입 — 라우트 2개만: `/`, `/incidents/:id`
  - fetch 클라이언트는 지금은 `openapi-fetch` 도입 없이 얇은 fetch 래퍼 함수 하나로 시작한다.
    여러 엔드포인트가 붙기 시작하는 시점(Phase 2~3 완료 후)에 openapi-typescript 도입을 재검토한다 — 지금
    도입하면 백엔드 OpenAPI 스펙이 바뀔 때마다 재생성 비용이 드는데, 아직 스펙이 안정되지 않았다.
  - `/` 화면에서 목업 대신 실제 `GET /incidents` 호출 → 3개 사건을 카드/리스트로 렌더
- **완료 조건**: 화면 로드 시 백엔드에서 실제로 3개 사건(적체/파업/관세)이 내려와 표시되고, 클릭하면
  `/incidents/:id`로 이동한다.

## Phase 2 — Impact DAG 실연동 (스키마 재정렬)

- **백엔드**: `GET /incidents/{id}/impact-dag` — 완성. 실제 응답 필드(확인됨):
  ```python
  ImpactDagNodeRead: node_key, label, affected_target, expected_time, basis, responsible_party, uncertainty
  ImpactDagEdgeRead: from_node_id, to_node_id, basis
  ```
- **기존 목업과의 차이 (재정렬 대상)**:
  - `entityType`(항만/부품/생산라인/운송/딜러), `evidenceType`(FACT/INFERENCE/ASSUMPTION) 필드는
    백엔드에 없다 — UI에서 제거하거나, 나중에 백엔드에 필드 추가를 요청할지 결정 필요(지금은 제거하고 진행)
  - 지연일수·비용 뱃지("+1.5일ㆍ996.1억원")는 DAG 노드 테이블 자체에 없는 값이다 — 시뮬레이션 결과
    계층(Phase 4)에서 나오는 값으로 추정된다. Phase 2에서는 이 뱃지를 숨긴다(자리는 유지, 데이터 없음
    표시)
  - 실제 시드 데이터는 노드 4~6개로 "생산라인 중단"에서 끝난다 — 지금 목업의 PCTC 해상운송→브레머하펜→
    유럽 딜러 3권역까지 이어지는 체인과 내용이 다르다. Phase 2 완료 후 목업 데이터를 실제 시드 3종 내용에
    맞게 다시 작성한다.
- **범위**: `types.ts`의 `ImpactDagNode`/`ImpactDagEdge`를 위 실제 스키마로 교체, `DagNode` 컴포넌트에서
  `entityType` 라벨과 지연/비용 뱃지 렌더링 제거(임시), 노드 클릭 상세 패널을 `basis`/`uncertainty`/
  `responsible_party` 실제 값으로 교체
- **완료 조건**: `/incidents/:id`에서 실제 DAG가 그려지고, 노드 클릭 시 실제 `basis`/`uncertainty` 값이
  상세 패널에 표시된다.

## Phase 3 — 운영 스냅샷 상태 표시

- **백엔드**: `GET /incidents/{id}/snapshots/latest` — 완성 (`OperationalSnapshotRead`)
- **범위**: 대시보드에 스냅샷 버전/시나리오 버전/quality_mode를 표시하는 영역 추가 (현재 와이어프레임에는
  없던 영역 — `simulation-supply-chain-tool.md` §3.3 데이터 품질 게이트 요구사항)
- **완료 조건**: 화면에 현재 스냅샷의 데이터 버전·시나리오 버전·품질 모드가 실제 값으로 표시된다.

## Phase 4 — docker-compose에 frontend 서비스 편입

- 기능이 아니라 인프라 정합성 문제 — `ARCHITECTURE.md` §1-6 "모든 인프라는 Docker Compose로 구성한다"
  원칙과 달리 지금은 로컬 `npm run dev`로만 개발 중이다.
- **범위**: `frontend/Dockerfile` 작성, `docker-compose.yml`에 `frontend` 서비스 추가(볼륨 마운트+HMR,
  `backend` healthcheck 이후 기동)
- **완료 조건**: `docker compose up`만으로 db/backend/frontend가 함께 뜨고 `http://localhost:5173`에서
  Phase 1~3까지의 화면이 그대로 동작한다.

---

## 이후 페이즈 (백엔드 API 대기 — 순서만 확정, 착수는 해당 API가 생긴 뒤)

| 페이즈 | 기능 | 필요한 백엔드 API |
|---|---|---|
| Phase 5 | 대응안 후보 비교·시뮬레이션 | `POST /incidents/{id}/simulate`, `GET .../candidates` |
| Phase 6 | 의사결정 근거 패널 | `GET /incidents/{id}/decision-package` |
| Phase 7 | 담당자 승인 | `POST /incidents/{id}/approvals` |
| Phase 8 | SOP 배포·미리보기 | `POST /approvals/{id}/dispatch-sop`, `GET .../sop-status` |
| Phase 9 | 실행 추적 타임라인 | `GET /incidents/{id}/timeline` |
| Phase 10 | 사후보고서 | `GET /incidents/{id}/post-report` |
| Phase 11 | ROI·비용 귀속 | `GET /reports/roi`, `GET .../cost-attribution` |

Phase 5~11은 현재 대시보드(`IncidentDashboard`)의 대응안 랭킹/SOP/승인 패널이 이미 UI로는 존재하므로,
해당 API가 생기면 그 패널의 데이터 소스만 목업에서 실제 호출로 바꾸면 된다 — 화면을 새로 만드는 작업이
아니라 배선(wiring)만 남는 상태로 유지하는 것이 목표.

## 다음 액션

Phase 1부터 순서대로 진행한다. Phase 2의 스키마 재정렬 항목(엔티티 타입/지연·비용 뱃지 제거)은 별도
합의 없이 이 문서 기준으로 바로 반영한다 — 백엔드 세션에는 Phase 5(대응안·시뮬레이션 API)부터 필요
목록을 전달한다.
