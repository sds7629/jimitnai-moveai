import { useEffect, useState } from "react";
import { getRoi } from "../features/roi/api";
import { ROI_SCENARIO_ORDER, type RoiApiResponse } from "../features/roi/types";
import { formatKrwToEokwon } from "../lib/currency";
import { useTheme } from "../lib/useTheme";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; roi: RoiApiResponse };

const SCENARIO_LABEL_COLOR: Record<(typeof ROI_SCENARIO_ORDER)[number], string> = {
  낙관: "text-[var(--teal)]",
  기준: "text-[var(--text-primary)]",
  보수: "text-[var(--amber)]",
};

/**
 * 연간 ROI 화면 (frontend/docs/FEATURE_PHASES.md Phase 12).
 *
 * GET /reports/roi는 사건에 종속되지 않는 전역 계산이라 개별 사건 화면이 아니라
 * 사건 목록과 나란한 최상위 라우트(/reports/roi)로 둔다. 낙관/기준/보수 3개 시나리오를
 * 항상 함께 보여줘서 단일 확정 수치처럼 보이지 않게 하고, disclosure(공개 통계 미확보 등)를
 * 각주로 숨기지 않는다.
 */
export function RoiPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const { theme } = useTheme();

  useEffect(() => {
    let cancelled = false;
    getRoi()
      .then((roi) => {
        if (!cancelled) setState({ status: "success", roi });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({ status: "error", message: error instanceof Error ? error.message : "알 수 없는 오류" });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return (
      <div data-theme={theme} className="min-h-screen bg-[var(--bg-page)] p-7 text-[var(--text-secondary)]">
        불러오는 중...
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div data-theme={theme} className="min-h-screen bg-[var(--bg-page)] p-7 text-[var(--red)]">
        연간 ROI를 불러오지 못했습니다: {state.message}
      </div>
    );
  }

  const { scenarios, disclosure } = state.roi;

  return (
    <div data-theme={theme} className="min-h-screen bg-[var(--bg-page)] p-7 text-[var(--text-primary)]">
      <div className="mb-5 text-[19px] font-bold">연간 ROI</div>

      <div className="mb-5 flex gap-4">
        {ROI_SCENARIO_ORDER.map((key) => {
          const scenario = scenarios[key];
          return (
            <div key={key} className="flex-1 rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
              <div className={`mb-2 text-[13.5px] font-bold ${SCENARIO_LABEL_COLOR[key]}`}>{key}</div>
              <div className="text-[10.5px] text-[var(--text-tertiary)]">연간 방어 가능 기대손실</div>
              <div className="mb-2 text-[15px] font-bold">
                {formatKrwToEokwon(scenario.annual_defendable_expected_loss)}
              </div>
              <div className="text-[10.5px] text-[var(--text-tertiary)]">연간 실현 절감액</div>
              <div className="mb-2 text-[15px] font-bold text-[var(--teal)]">
                {formatKrwToEokwon(scenario.annual_realized_savings)}
              </div>
              <div className="text-[10.5px] text-[var(--text-tertiary)]">투자 회수기간</div>
              <div className="text-[15px] font-bold">
                {scenario.payback_period_days !== null ? `${Math.round(scenario.payback_period_days)}일` : "-"}
              </div>
              {scenario.payback_note && (
                <div className="mt-1 text-[10px] text-[var(--red)]">{scenario.payback_note}</div>
              )}
              <div className="mt-3 text-[9.5px] text-[var(--text-tertiary)]">
                개입가능 {Math.round(scenario.adjusted_intervention_ratio * 100)}% · 실행률{" "}
                {Math.round(scenario.adjusted_execution_rate * 100)}% · 손실감소율{" "}
                {Math.round(scenario.adjusted_loss_reduction_rate * 100)}%
              </div>
            </div>
          );
        })}
      </div>

      <div className="rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
        <div className="mb-2 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">
          공개사항 {disclosure.validation_required_before_real_data && "(실제 데이터 검증 필요)"}
        </div>
        <ul className="flex flex-col gap-1.5 text-[10.5px] text-[var(--text-secondary)]">
          <li>{disclosure.public_statistics_source}</li>
          <li>{disclosure.frequency_and_loss_basis}</li>
          <li>{disclosure.direct_vs_customer_avoidance}</li>
          <li>{disclosure.included_excluded_cost_items}</li>
          <li>{disclosure.scenario_adjustment_basis}</li>
        </ul>
      </div>
    </div>
  );
}
