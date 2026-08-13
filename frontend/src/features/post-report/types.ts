/**
 * GET /incidents/{id}/post-report, GET /incidents/{id}/cost-attribution 응답 타입.
 * backend/app/schemas/post_report.py를 그대로 옮겼다 (Phase 11).
 *
 * 이 시스템엔 실적 확정값을 입력받는 API가 없어서 report_status는 항상 "잠정",
 * actual_status는 항상 "미확정"이다(backend/app/services/post_report.py 모듈 docstring) —
 * 화면에서 이 제약을 숨기지 않고 그대로 노출해야 한다.
 */
import type { ExclusionCategory, ValidationStatus } from "../candidates/types";

export interface PostReportApi {
  incident_id: number;
  report_status: string;
  actual_status: string;
  scope_limitation_note: string;
  generated_at: string;
  sections: Record<string, unknown>;
}

/** simulation-supply-chain-tool.md §8.2 12개 섹션 — build_post_report의 실제 키 순서 그대로 */
export const POST_REPORT_SECTIONS: { key: string; label: string }[] = [
  { key: "1_사건_개요와_발생시점", label: "1. 사건 개요와 발생시점" },
  { key: "2_최초_예상과_실제_진행_과정", label: "2. 최초 예상과 실제 진행 과정" },
  { key: "3_주요_동적_변수의_변화", label: "3. 주요 동적 변수의 변화" },
  { key: "4_검토한_대응안과_제외_사유", label: "4. 검토한 대응안과 제외 사유" },
  { key: "5_최종_결정과_승인자", label: "5. 최종 결정과 승인자" },
  { key: "6_SOP_발송_수신_수락_실행_이력", label: "6. SOP 발송·수신·수락·실행 이력" },
  { key: "7_예상_손실과_실제_손실", label: "7. 예상 손실과 실제 손실" },
  { key: "8_회피한_손실과_추가_발생_비용", label: "8. 회피한 손실과 추가 발생 비용" },
  { key: "9_LD_DND_귀책_및_비용_부담_주체", label: "9. LD·D&D 귀책 및 비용 부담 주체" },
  { key: "10_시뮬레이션_오차와_가정의_영향", label: "10. 시뮬레이션 오차와 가정의 영향" },
  {
    key: "11_자원_확보_실패_실행_편차와_에스컬레이션_이력",
    label: "11. 자원 확보 실패·실행 편차와 에스컬레이션 이력",
  },
  { key: "12_향후_SOP_모델_데이터_개선사항", label: "12. 향후 SOP·모델·데이터 개선사항" },
];

/**
 * GET /incidents/{id}/cost-attribution 응답.
 * breakdown은 항상 이 3개 키를 갖는다: "직접_손익_효과" / "고객_회피비용" / "분쟁_협상_가능_금액"
 * (backend/app/services/cost_attribution.py DIRECT_PL_KEY 등). is_heuristic이 true인 한
 * heuristic_disclaimer("법무 판단 대체 아님")를 화면에서 생략하면 안 된다.
 */
export interface CostAttributionApi {
  incident_id: number;
  is_heuristic: boolean;
  rag_unavailable: boolean;
  heuristic_disclaimer: string;
  avoided_loss_basis: Record<string, unknown>;
  matched_ld_clauses: Record<string, unknown>[];
  matched_dnd_clauses: Record<string, unknown>[];
  breakdown: Record<string, number | null>;
  classification_note: string;
}

export const COST_ATTRIBUTION_LABELS: { key: string; label: string }[] = [
  { key: "직접_손익_효과", label: "직접 손익 효과" },
  { key: "고객_회피비용", label: "고객 회피비용" },
  { key: "분쟁_협상_가능_금액", label: "분쟁·협상 가능 금액" },
];

/**
 * Phase 19 전용 타입 — sections["1_사건_개요와_발생시점"]의 실제 형태
 * (backend/app/services/post_report.py _section_1_overview 확인).
 */
export interface OverviewSection {
  incident_id: number;
  type: string;
  location: string;
  occurred_at: string;
  status: string;
  duplicate_of_incident_id: number | null;
  affected_targets: Record<string, unknown>;
  assumptions_at_intake: string[];
  created_at: string;
}

/**
 * Phase 19/20/23 공용 타입 — _approval_summary / _candidate_summary가 만드는 형태
 * (backend/app/services/post_report.py 확인). candidate_summary는 후보 자체가 없으면
 * {available:false}뿐이고, 있으면 시뮬레이션 유무에 따라 simulation 필드가 갈린다.
 */
export interface ApprovalSummaryApi {
  approval_id: number;
  decision_type: string;
  reason: string;
  approver: string;
  decided_at: string;
  data_version_ref: string | null;
  scenario_version_ref: string | null;
}
export type FinalDecisionApi = { available: false; reason: string } | ({ available: true } & ApprovalSummaryApi);

export interface FinalDecisionSection {
  approvals_history: ApprovalSummaryApi[];
  final_decision: FinalDecisionApi;
}

export interface CandidateSimulationApi {
  available: boolean;
  reason?: string;
  expected_loss?: number | null;
  p90?: number | null;
  cvar?: number | null;
  confidence?: number | null;
  data_version?: string;
  scenario_version?: string;
  calculated_at?: string;
}
export type CandidateSummaryApi =
  | { available: false }
  | {
      available: true;
      candidate_id: number;
      candidate_type: string;
      description: string;
      start_time_variant: string | null;
      simulation: CandidateSimulationApi;
    };

/**
 * Phase 21 전용 타입 — sections["4_검토한_대응안과_제외_사유"]의 실제 형태
 * (backend/app/services/post_report.py _section_4_candidates_reviewed 확인).
 * validation_status가 "가능"이 아닌 후보를 제외로 세기 때문에 "미검증"도 excluded_count에 포함된다.
 */
export interface ReviewedCandidateApi {
  candidate_id: number;
  candidate_type: string;
  description: string;
  start_time_variant: string | null;
  validation_status: ValidationStatus;
  exclusion_category: ExclusionCategory | null;
  exclusion_detail: string | null;
  preconditions: string[];
}

export interface CandidatesReviewedSection {
  total_count: number;
  excluded_count: number;
  candidates: ReviewedCandidateApi[];
}

/**
 * Phase 20 전용 타입 — sections["2_최초_예상과_실제_진행_과정"]의 실제 형태
 * (backend/app/services/post_report.py _section_2_expected_vs_actual_progress 확인).
 *
 * actual_progress는 _unavailable(SCOPE_LIMITATION_NOTE)이라 항상 available:false다 —
 * 실적 확정 API가 없다는 건 이 시스템의 의도된 스코프 제약이므로 reason을 화면에서 숨기지 않는다.
 */
export interface ExpectedProgressApi {
  baseline: CandidateSummaryApi;
  approved_candidate: CandidateSummaryApi;
}

export interface UnavailableWithReasonApi {
  available: false;
  reason: string;
}

export interface ExpectedVsActualProgressSection {
  expected: ExpectedProgressApi;
  actual_status: string;
  actual_progress: UnavailableWithReasonApi;
}

/**
 * Phase 20 전용 타입 — sections["3_주요_동적_변수의_변화"]의 실제 형태
 * (backend/app/services/post_report.py _section_3_dynamic_variable_changes 확인).
 */
export interface SnapshotVersionApi {
  snapshot_id: number;
  data_version: string;
  scenario_version: string;
  quality_mode: string;
  freshness_seconds: number | null;
  coverage_ratio: number | null;
  assumptions: string[];
  created_at: string;
}

export interface SnapshotChangeApi {
  from_snapshot_id: number;
  to_snapshot_id: number;
  from_created_at: string;
  to_created_at: string;
  summary: string;
}

/**
 * _summarize_snapshot_changes는 스냅샷 이력이 0~1개면 안내 문구 string[]을,
 * 2개 이상이면 버전 간 diff 객체 배열을 반환한다 — 유니온으로 받고 화면에서 분기한다.
 */
export interface DynamicVariableChangesSection {
  snapshot_count: number;
  versions: SnapshotVersionApi[];
  changes_summary: string[] | SnapshotChangeApi[];
}

/**
 * Phase 23 전용 타입 — sections["7_예상_손실과_실제_손실"]의 실제 형태
 * (backend/app/services/post_report.py _section_7_expected_vs_actual_loss 확인).
 * expected_loss는 섹션 2의 ExpectedProgressApi(baseline/승인후보)를 그대로 재사용한다.
 */
export interface ExpectedVsActualLossSection {
  expected_loss: ExpectedProgressApi;
  actual_status: string;
  actual_loss: UnavailableWithReasonApi;
}

/**
 * Phase 23 전용 타입 — backend/app/services/cost_attribution.py
 * compute_expected_avoided_loss()가 만드는 형태. baseline/승인 후보 중 하나라도 없거나
 * 시뮬레이션 결과가 없으면 available:false + reason, 있으면 available:true + amount(양수=절감) + note.
 */
export interface AvoidedLossCandidateRefApi {
  candidate_id: number;
  candidate_type: string;
  description: string;
  expected_loss: number | null;
  data_version: string | null;
  scenario_version: string | null;
  calculated_at: string | null;
  has_simulation_result: boolean;
}

export type ExpectedAvoidedLossApi =
  | {
      available: false;
      amount: null;
      baseline: AvoidedLossCandidateRefApi | null;
      approved: AvoidedLossCandidateRefApi | null;
      reason: string;
    }
  | {
      available: true;
      amount: number;
      baseline: AvoidedLossCandidateRefApi | null;
      approved: AvoidedLossCandidateRefApi | null;
      reason: null;
      note: string;
    };

/**
 * Phase 23 전용 타입 — sections["8_회피한_손실과_추가_발생_비용"]의 실제 형태
 * (backend/app/services/post_report.py _section_8_avoided_loss 확인).
 */
export interface AvoidedLossSection {
  expected_avoided_loss: ExpectedAvoidedLossApi;
  additional_cost_incurred: UnavailableWithReasonApi;
}
