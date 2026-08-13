# 프론트엔드 기능 정의 및 페이즈 분리

`FRONTEND_ARCHITECTURE.md` §3 라우팅 표와 `simulation-supply-chain-tool.md` §2 업무 흐름을 기준으로
필요한 기능을 전부 나열하고, 백엔드 진행 속도에 맞춰 기능 하나씩 순서대로 진행한다.

## 원칙

- **기능 하나 = 페이즈 하나.** 한 페이즈 안에서 여러 화면을 동시에 벌리지 않는다.
- **백엔드가 이미 만든 API가 있는 기능부터.** 없는 기능은 목업을 유지한 채 뒤로 미룬다.
- **스키마는 무겁게 계약 협상하지 않고, 백엔드가 실제로 응답하는 필드에 맞춰 가볍게 realign한다.**
  백엔드 속도가 빠르므로 문서로 먼저 스펙을 고정하기보다 실제 Pydantic 스키마를 그때그때 확인해서 맞춘다.
- 각 페이즈는 "완료 조건"을 명시한다 — 완료 조건을 만족하면 다음 페이즈로 넘어간다.

## 전체 기능 목록과 현재 상태 (2번째 검토)

`ARCHITECTURE.md` §7.1 표의 10개 워크플로 화면 기준. 최초 작성 이후 백엔드가 대응 설계·제약 검증·
시뮬레이션·의사결정 최적화·오케스트레이션(승인 상태머신 + SSE) 웨이브를 전부 병합해서, 상태가 크게
바뀌었다.

| # | 기능 | 백엔드 API | 상태 |
|---|---|---|---|
| 1 | 사건 목록 (시드 시나리오 선택) | `GET /incidents` | ✅ **완료** (Phase 1) |
| 2 | Impact DAG 시각화 | `GET /incidents/{id}/impact-dag` | ✅ **완료** (Phase 2) |
| 3 | 운영 스냅샷 상태 (freshness/coverage) | `GET /incidents/{id}/snapshots/latest` | ✅ **완료** (Phase 3) |
| 4 | 대응안 후보 비교·시뮬레이션 | `POST /incidents/{id}/simulate`, `GET .../candidates` | ✅ 있음 — 착수 가능 (Phase 5) |
| 5 | 의사결정 근거 패널 | `GET /incidents/{id}/decision-package` | ✅ 있음 — 착수 가능 (Phase 6) |
| 6 | 담당자 승인 | `POST /incidents/{id}/approvals` | ✅ 있음 — 착수 가능 (Phase 7) |
| 7 | 실시간 갱신 (SSE) | `GET /incidents/{id}/stream` | ✅ 있음 — 착수 가능 (Phase 8) |
| 8 | SOP 배포·미리보기 | `POST /approvals/{id}/dispatch-sop`, `GET .../sop-status` | ❌ 없음 |
| 9 | 실행 추적 타임라인 | `GET /incidents/{id}/timeline` | ❌ 없음 (`audit_log` 테이블은 있음) |
| 10 | 사후보고서 | `GET /incidents/{id}/post-report` | ❌ 없음 |
| 11 | ROI·비용 귀속 | `GET /reports/roi`, `GET .../cost-attribution` | ❌ 없음 |

**요약**: 1~7번(진입~승인, SSE까지)이 전부 실연동 가능한 상태다. 남은 건 SOP/타임라인/사후보고서/ROI
4개뿐이고, 이 4개는 여전히 백엔드 라우터가 없다.

---

## Phase 1 — 사건 목록 (진입 화면) ✅ 완료

`GET /incidents`. 시드 3종을 목록으로 렌더링, 클릭 시 `/incidents/:id`로 이동. react-router 최소 도입,
얇은 fetch 래퍼(`src/lib/apiClient.ts`) 도입.

## Phase 2 — Impact DAG 실연동 ✅ 완료

`GET /incidents/{id}/impact-dag`. 위상정렬로 flat한 노드/엣지를 좌→우 컬럼에 배치(`layoutDagIntoColumns`).
`entityType`/지연·비용 뱃지는 실제 스키마에 없어서 제거, 노드 상세 패널을 `basis`/`uncertainty`/
`responsible_party`/`affected_target`/`expected_time` 실제 값으로 교체.

## Phase 3 — 운영 스냅샷 상태 표시 ✅ 완료

`GET /incidents/{id}/snapshots/latest`. `quality_mode`/`freshness_seconds`/`coverage_ratio`를
사람이 읽을 수 있는 문구로 변환(`summarizeSnapshot`)해서 대시보드 상단에 상태 바로 표시.

## Phase 4 — docker-compose에 frontend 서비스 편입 (미착수)

- 기능이 아니라 인프라 정합성 문제 — 지금은 로컬 `npm run dev`로만 개발 중이라 `ARCHITECTURE.md` §1-6
  "모든 인프라는 Docker Compose로 구성한다" 원칙과 어긋난 채로 있다.
- **범위**: `frontend/Dockerfile` 작성, `docker-compose.yml`에 `frontend` 서비스 추가
- **완료 조건**: `docker compose up`만으로 db/backend/frontend가 함께 뜨고 지금까지의 화면이 그대로 동작

---

## Phase 5 — 대응안 후보 비교·시뮬레이션 (신규 착수 가능)

- **백엔드**: `POST /incidents/{id}/simulate` (파이프라인 재실행), `GET /incidents/{id}/candidates`
  (결과 조회) — 완성. 실제 응답 필드(확인됨, `backend/app/schemas/simulate.py`):
  ```python
  CandidateWithLatestSimulation:
    candidate_type, description, validation_status, exclusion_category, exclusion_detail,
    preconditions, start_time_variant, latest_simulation: SimulationResultRead | None

  SimulationResultRead:
    expected_loss, p90, cvar, sensitivity_variables, confidence,
    fact, inference, assumption   # 각각 dict — FACT/INFERENCE/ASSUMPTION이 실제로 존재한다!
  ```
- **기존 목업과의 차이**: `mockData.ts`의 `ResponseCandidate`(rank/savingsAmount/remainingLoss/
  mitigationRatio)는 실제 응답과 필드명·구조가 다르다 — "잔여손실 개별 vs 누적" 논쟁(Phase 2 완료 시점
  미해결 이슈)도 실제로는 랭킹 개념 자체가 없고, 후보별 `latest_simulation`(expected_loss/p90/cvar)을
  프론트에서 정렬해서 보여주는 구조로 재설계해야 한다. `제외된 대응안`은 `validation_status`가
  실행불가인 후보 + `exclusion_category`/`exclusion_detail`로 그대로 매핑 가능.
- **범위**: 실제 스키마 기준 타입 재작성, `POST /simulate` 트리거 버튼(기존 "다시 실행"을 이 용도로
  재배선하거나 별도 버튼 추가), `GET /candidates`로 목록 조회 후 화면에 렌더링. P90/CVaR 자리표시자
  칸을 실제 차트로 교체(Recharts 도입 시점).
- **완료 조건**: 실제 대응안 후보와 각 후보의 기대손실/P90/CVaR/FACT·INFERENCE·ASSUMPTION이 화면에
  표시된다.

## Phase 6 — 의사결정 근거 패널 (신규 착수 가능)

- **백엔드**: `GET /incidents/{id}/decision-package` — 완성. `package` 필드가
  `simulation-supply-chain-tool.md` §5.1의 10개 항목을 정확히 그대로 담고 있다(확인됨,
  `backend/app/services/response_optimization.py`):
  ```python
  package: {
    "expected_loss_p90_cvar", "now_vs_6h_vs_no_action", "causal_path",
    "data_and_documents_used", "fact_inference_assumption", "freshness_and_coverage",
    "key_sensitivity_variables", "feasibility_and_exclusion", "confidence_and_uncertainty",
    "recommended_deadline": {"deadline", "detail"},
    "ranked_candidates": {"ranked", "excluded_from_ranking"},
    "disclaimer",
  }
  recommended_deadline: datetime | None   # DecisionPackageRead 최상위 필드에도 별도로 있음
  ```
- **의미**: 이 문서 §5.1이 요구한 항목(P90/CVaR, 지금/6시간후/무대응 비교, 원인 경로, 사용 데이터,
  FACT/INFERENCE/ASSUMPTION, freshness/coverage, 민감도 변수, 실행가능성/제외사유, 신뢰도/불확실성,
  결정기한)이 **하나도 빠짐없이** 이미 백엔드에 구현돼 있다 — Phase 2~3에서 프론트가 따로 만들어야 하나
  걱정했던 부분(P90/CVaR 자리표시자, 결정기한 카운트다운)이 전부 이 한 엔드포인트로 해결된다.
- **범위**: `decision-package` 응답을 그대로 렌더링하는 패널 신규 작성(10개 섹션), `recommended_deadline`
  기준 카운트다운 UI
- **완료 조건**: 사건 상세 화면에서 의사결정 근거 10개 항목이 실제 값으로 표시된다.

## Phase 7 — 담당자 승인 (신규 착수 가능)

- **백엔드**: `POST /incidents/{id}/approvals` — 완성. 클라이언트가 보낼 수 있는 `decision_type`은
  정확히 4개(`승인`/`조건부승인`/`수정요청`/`반려`) — 지금 프론트의 `ApprovalAction`
  (`approve`/`conditional`/`revise`/`reject`)와 값 자체(영문 vs 한글)만 다르고 개념은 이미 1:1로
  맞아떨어진다. `조건부승인`은 `reason`이 10자 이상이어야 하는 서버 검증이 있다(`기한초과`는
  시스템 전용이라 클라이언트가 보낼 수 없음).
- **범위**: 승인 액션 패널에 사유(`reason`)·승인자(`approver`) 입력 폼 추가(현재는 버튼만 있고 사유
  입력 폼이 없음), 조건부승인 시 최소 10자 검증을 프론트에서도 선제 표시
- **완료 조건**: 승인/조건부승인/수정요청/반려 버튼 클릭 시 실제 `POST /approvals` 호출이 성공하고
  결과가 반영된다.

## Phase 8 — 실시간 갱신 (SSE) (신규 착수 가능)

- **백엔드**: `GET /incidents/{id}/stream` — 완성. 2~3초 간격 폴링 기반 SSE, 이벤트 타입 3종:
  `decision_package_updated`, `dag_updated`, `deadline_overrun` (원래 `FRONTEND_ARCHITECTURE.md`
  §4에서 계획했던 `sop_status_changed`는 SOP 웨이브가 아직 없어서 제외됨)
- **범위**: `useIncidentStream(incidentId)` 훅 작성(`EventSource` 구독), 이벤트 타입별로 해당 화면
  영역만 재조회. TanStack Query 없이 지금 구조(로컬 `useState` + `useEffect` fetch)로는 "필요한
  부분만 무효화"가 번거로우므로, 이 페이즈 시점에 TanStack Query 도입을 재검토한다(Phase 1에서
  "엔드포인트 여러 개 붙으면 재검토"라고 미뤄뒀던 지점)
- **완료 조건**: 스냅샷/DAG가 서버에서 갱신되면 폴링 없이 화면이 자동으로 새로고침된다.

---

## 이후 페이즈 (여전히 백엔드 API 대기)

| 페이즈 | 기능 | 필요한 백엔드 API |
|---|---|---|
| Phase 9 | SOP 배포·미리보기 | `POST /approvals/{id}/dispatch-sop`, `GET .../sop-status` |
| Phase 10 | 실행 추적 타임라인 | `GET /incidents/{id}/timeline` |
| Phase 11 | 사후보고서 | `GET /incidents/{id}/post-report` |
| Phase 12 | ROI·비용 귀속 | `GET /reports/roi`, `GET .../cost-attribution` |

## 다음 액션

Phase 5(대응안·시뮬레이션)부터 순서대로 진행한다. Phase 4(docker-compose 편입)는 기능이 아니라
인프라 항목이라 우선순위상 뒤로 미뤄도 무방 — Phase 5~8 완료 후 한 번에 처리하는 것도 고려.
