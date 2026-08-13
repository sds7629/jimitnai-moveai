/**
 * GET /reports/roi 응답 타입. backend/app/services/roi.py compute_roi를 그대로 옮겼다 (Phase 12).
 * 사건에 종속되지 않는 전역 계산 — 낙관/기준/보수 3개 시나리오를 항상 함께 반환해서
 * 단일 확정 수치처럼 보이지 않게 한다.
 */
export interface RoiScenarioApi {
  adjusted_intervention_ratio: number;
  adjusted_execution_rate: number;
  adjusted_loss_reduction_rate: number;
  annual_defendable_expected_loss: number;
  annual_realized_savings: number;
  payback_period_days: number | null;
  /** payback_period_days가 null일 때만 채워지는 사유 */
  payback_note: string | null;
}

export const ROI_SCENARIO_ORDER = ["낙관", "기준", "보수"] as const;

export interface RoiDisclosureApi {
  public_statistics_source: string;
  frequency_and_loss_basis: string;
  direct_vs_customer_avoidance: string;
  included_excluded_cost_items: string;
  scenario_adjustment_basis: string;
  validation_required_before_real_data: boolean;
}

export interface RoiApiResponse {
  inputs: Record<string, number>;
  scenarios: Record<(typeof ROI_SCENARIO_ORDER)[number], RoiScenarioApi>;
  disclosure: RoiDisclosureApi;
}
