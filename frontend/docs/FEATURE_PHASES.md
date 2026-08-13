# 프론트엔드 기능 정의 및 페이즈 분리

`FRONTEND_ARCHITECTURE.md` §3 라우팅 표와 `simulation-supply-chain-tool.md` §2 업무 흐름을 기준으로
필요한 기능을 전부 나열하고, 백엔드 진행 속도에 맞춰 기능 하나씩 순서대로 진행한다.

## 원칙

- **기능 하나 = 페이즈 하나.** 한 페이즈 안에서 여러 화면을 동시에 벌리지 않는다.
- **백엔드가 이미 만든 API가 있는 기능부터.** 없는 기능은 목업을 유지한 채 뒤로 미룬다.
- **스키마는 무겁게 계약 협상하지 않고, 백엔드가 실제로 응답하는 필드에 맞춰 가볍게 realign한다.**
  백엔드 속도가 빠르므로 문서로 먼저 스펙을 고정하기보다 실제 Pydantic 스키마를 그때그때 확인해서 맞춘다.
- 각 페이즈는 "완료 조건"을 명시한다 — 완료 조건을 만족하면 다음 페이즈로 넘어간다.

## 전체 기능 목록과 현재 상태 (3번째 검토)

`ARCHITECTURE.md` §7.1 표의 10개 워크플로 화면 기준. 백엔드가 8개 웨이브(대응 설계·제약 검증·
시뮬레이션·의사결정 최적화·오케스트레이션·커뮤니케이션-SOP·실행추적·**사후보고**)를 전부 병합해서,
**백엔드는 이제 전체 워크플로를 다 구현했다.**

| # | 기능 | 백엔드 API | 상태 |
|---|---|---|---|
| 1 | 사건 목록 (시드 시나리오 선택) | `GET /incidents` | ✅ **완료** (Phase 1) |
| 2 | Impact DAG 시각화 | `GET /incidents/{id}/impact-dag` | ✅ **완료** (Phase 2) |
| 3 | 운영 스냅샷 상태 (freshness/coverage) | `GET /incidents/{id}/snapshots/latest` | ✅ **완료** (Phase 3) |
| 4 | 대응안 후보 비교·시뮬레이션 | `POST /incidents/{id}/simulate`, `GET .../candidates` | ✅ **완료** (Phase 5) |
| 5 | 의사결정 근거 패널 | `GET /incidents/{id}/decision-package` | ✅ **완료** (Phase 6) |
| 6 | 담당자 승인 | `POST /incidents/{id}/approvals` | ✅ **완료** (Phase 7) |
| 7 | 실시간 갱신 (SSE) | `GET /incidents/{id}/stream` | ✅ **완료** (Phase 8) |
| 8 | SOP 배포·상태 | `POST /approvals/{id}/dispatch-sop`, `GET .../sop-status` | ✅ **완료** (Phase 9) |
| 9 | 실행 추적 타임라인·상태 전이 | `PATCH /sop/{sop_id}/status`, `GET .../timeline` | ✅ **완료** (Phase 10) |
| 10 | 사후보고서 + 비용 귀속 | `GET .../post-report`, `GET .../cost-attribution` | ✅ 있음 — 착수 가능 (Phase 11) |
| 11 | 연간 ROI | `GET /reports/roi` | ✅ 있음 — 착수 가능 (Phase 12) |

Docker 편입(Phase 4)까지 포함하면 **Phase 1~12 전부 착수 가능한 상태**다 — 이 문서가 처음 만들어진
뒤로 처음으로 "백엔드 대기" 항목이 하나도 안 남았다.

---

## Phase 1 — 사건 목록 (진입 화면) ✅ 완료

`GET /incidents`. 시드 3종을 목록으로 렌더링, 클릭 시 `/incidents/:id`로 이동. react-router 최소 도입,
얇은 fetch 래퍼(`src/lib/apiClient.ts`) 도입.

## Phase 2 — Impact DAG 실연동 ✅ 완료

`GET /incidents/{id}/impact-dag`. 위상정렬로 flat한 노드/엣지를 좌→우 컬럼에 배치(`layoutDagIntoColumns`).

## Phase 3 — 운영 스냅샷 상태 표시 ✅ 완료

`GET /incidents/{id}/snapshots/latest`. `summarizeSnapshot`으로 사람이 읽을 수 있는 문구로 변환.

## Phase 4 — docker-compose에 frontend 서비스 편입 ✅ 완료

`frontend/Dockerfile` + `docker-compose.yml` frontend 서비스. `docker compose up`으로 4개 컨테이너
전부 healthy, end-to-end(curl로 시드 사건 조회까지) 검증 완료.

## Phase 5 — 대응안 후보 비교·시뮬레이션 ✅ 완료

`POST /incidents/{id}/simulate`, `GET /incidents/{id}/candidates`. `mapCandidatesToDashboard`로
기대손실 오름차순 정렬, baseline 대비 절감액/완화율 계산. "다시 실행" 버튼이 실제 파이프라인을 트리거.

## Phase 6 — 의사결정 근거 패널 ✅ 완료

`GET /incidents/{id}/decision-package`. §5.1의 10개 항목을 `DecisionPackagePanel`로 그대로 렌더링,
`recommended_deadline` 카운트다운(`summarizeDeadline`) 포함.

## Phase 7 — 담당자 승인 ✅ 완료

`POST /incidents/{id}/approvals`. 사유·승인자 입력 폼, 조건부승인 10자 검증(서버와 동일 기준 선제 검증).

## Phase 8 — 실시간 갱신 (SSE) ✅ 완료

`GET /incidents/{id}/stream`. `useIncidentStream` 훅으로 `dag_updated`/`decision_package_updated`/
`deadline_overrun` 3종 이벤트 구독, 이벤트별 부분 재조회.

## Phase 9 — SOP 배포·상태 ✅ 완료

`POST /approvals/{id}/dispatch-sop`, `GET /incidents/{id}/sop-status`. 승인/조건부승인 성공 시 자동
발송, 역할별(항만/운송/공장/영업/계약) 발송 상태를 `SopDispatchPanel`로 표시.

## Phase 10 — 실행 추적 타임라인·상태 전이 ✅ 완료

`PATCH /sop/{sop_id}/status`, `GET /incidents/{id}/timeline`. 역할별 상태를 수신/수락/시작/진행/완료/
실패로 전이, 편차 감지 시(`deviation_check`) DAG·후보·의사결정 패키지까지 전체 재조회.

---

## Phase 11 — 사후보고서 + 비용 귀속 (신규 착수 가능)

- **백엔드**: `GET /incidents/{id}/post-report`, `GET /incidents/{id}/cost-attribution` — 완성.
  실제 응답 필드(확인됨, `backend/app/schemas/post_report.py`):
  ```python
  PostReportRead:
    incident_id, report_status, actual_status, scope_limitation_note, generated_at,
    sections: dict[str, Any]   # 12개 키 전부 항상 존재

  CostAttributionRead:
    incident_id, is_heuristic, rag_unavailable, heuristic_disclaimer,
    avoided_loss_basis, matched_ld_clauses, matched_dnd_clauses,
    breakdown: {"직접_손익_효과", "고객_회피비용", "분쟁_협상_가능_금액"},
    classification_note
  ```
  `sections`의 12개 키(`backend/app/services/post_report.py` `build_post_report` 확인):
  ```text
  1_사건_개요와_발생시점
  2_최초_예상과_실제_진행_과정
  3_주요_동적_변수의_변화
  4_검토한_대응안과_제외_사유
  5_최종_결정과_승인자
  6_SOP_발송_수신_수락_실행_이력
  7_예상_손실과_실제_손실
  8_회피한_손실과_추가_발생_비용
  9_LD_DND_귀책_및_비용_부담_주체
  10_시뮬레이션_오차와_가정의_영향
  11_자원_확보_실패_실행_편차와_에스컬레이션_이력
  12_향후_SOP_모델_데이터_개선사항
  ```
- **중요한 스코프 제약(꼭 화면에 드러내야 함)**: 이 시스템엔 실적 확정값을 입력받는 API가 없어서
  `report_status`는 **항상 `"잠정"`**, `actual_status`는 **항상 `"미확정"`**이다. "회피한 손실"은 실측이
  아니라 baseline-승인후보 기대손실 차이로 계산한 **추정치**(`expected_avoided_loss`)이고, "시뮬레이션
  오차"는 계산 불가로 명시된다. `scope_limitation_note` 필드에 이 제약이 이미 문장으로 들어있으므로,
  화면 상단에 그대로 노출해서 "이 보고서는 확정본이 아니다"를 숨기지 않는다.
- **비용 귀속 분류도 안전한 휴리스틱**: `is_heuristic=true`, `heuristic_disclaimer` 필드가 "법무 판단
  대체가 아님"을 명시한다 — 이 문구도 화면에 그대로 노출한다. 근거 계약 조항 불명확 시 전액
  "분쟁_협상_가능_금액"으로 분류(직접손익으로는 절대 분류 안 함).
- **범위**: 새 라우트 `/incidents/:id/post-report`(기존 대시보드에 얹지 않고 별도 페이지로 분리 —
  사후 정산 성격상 진행 중 대시보드와 관심사가 다르고, `FRONTEND_ARCHITECTURE.md` §3 원래 라우팅
  표에도 별도 경로로 계획돼 있었다). decision-package와 같은 방식(섹션 라벨 + 내용 그대로 펼치기)으로
  12개 섹션 렌더링, cost-attribution의 3분류 breakdown을 강조 표시.
- **완료 조건**: `/incidents/:id/post-report`에서 12개 섹션과 비용 귀속 3분류가 실제 값으로 표시되고,
  "잠정" 상태·추정치 제약이 화면에 명시된다.

## Phase 12 — 연간 ROI (신규 착수 가능)

- **백엔드**: `GET /reports/roi` — 완성, **사건 독립적** 전역 엔드포인트. 실제 응답 필드(확인됨,
  `backend/app/services/roi.py`):
  ```python
  RoiRead:
    inputs: dict[str, float]                      # 계산에 쓰인 6개 파라미터
    scenarios: {"낙관": {...}, "기준": {...}, "보수": {...}}   # 각각 factor 적용된 결과
    disclosure: dict[str, Any]                      # 공개 통계 미확보 등 §10이 요구하는 공개사항
  ```
  기본 파라미터는 `simulation-supply-chain-tool.md` §10 예시값(연 500억/실제 방어율 30%/회수기간
  12일)을 역산해서 채택 — 확정치가 아니라 "공개 통계와 보수적 가정으로 만든 사업성 시나리오"임을
  `disclosure`가 명시한다.
- **범위**: 새 라우트 `/reports/roi` — 사건에 종속되지 않는 전역 화면이라 `IncidentListPage`처럼
  사건 목록과 나란히 있는 최상위 페이지로 추가. 낙관/기준/보수 3개 시나리오를 나란히 비교하는 카드,
  `disclosure` 공개사항을 각주로 표시.
- **완료 조건**: `/reports/roi`에서 3개 시나리오(낙관/기준/보수)의 연간 방어 가능 기대손실·실현
  절감액·투자 회수기간이 표시되고, 공개사항 각주가 함께 보인다.

## 다음 액션

Phase 11(사후보고서+비용귀속) → Phase 12(ROI) 순서로 진행한다. 둘 다 백엔드가 완성돼 있어 순서를
바꿔도 무방하지만, 사후보고서가 개별 사건 화면과 더 가깝고(같은 `/incidents/:id/*` 네임스페이스),
ROI는 완전히 별도 전역 화면이라 뒤에 붙이는 편이 자연스럽다.
