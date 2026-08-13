import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { RoiPage } from "../RoiPage";
import { getRoi } from "../../features/roi/api";
import type { RoiApiResponse, RoiScenarioApi } from "../../features/roi/types";

vi.mock("../../features/roi/api");
const mockGetRoi = vi.mocked(getRoi);

function scenario(overrides: Partial<RoiScenarioApi> = {}): RoiScenarioApi {
  return {
    adjusted_intervention_ratio: 0.5,
    adjusted_execution_rate: 0.6,
    adjusted_loss_reduction_rate: 0.5,
    annual_defendable_expected_loss: 50_000_000_000,
    annual_realized_savings: 15_000_000_000,
    payback_period_days: 12,
    payback_note: null,
    ...overrides,
  };
}

const roiResponse: RoiApiResponse = {
  inputs: {
    annual_incident_frequency: 20,
    expected_loss_per_incident: 5_000_000_000,
    intervention_ratio: 0.5,
    execution_rate: 0.6,
    loss_reduction_rate: 0.5,
    total_investment: 490_000_000,
  },
  scenarios: {
    낙관: scenario({ annual_realized_savings: 20_000_000_000, payback_period_days: 9 }),
    기준: scenario(),
    보수: scenario({ annual_realized_savings: 10_000_000_000, payback_period_days: 18 }),
  },
  disclosure: {
    public_statistics_source: "미확보 -- 실제 공개 통계 원문과 기준연도는 연결되어 있지 않습니다.",
    frequency_and_loss_basis: "미확보 -- 실측 산출 근거 데이터가 없습니다.",
    direct_vs_customer_avoidance: "이 엔드포인트는 총 절감액만 계산합니다.",
    included_excluded_cost_items: "포함: total_investment 단일 합계 전체.",
    scenario_adjustment_basis: "낙관 = 기준 x 1.2, 보수 = 기준 x 0.8",
    validation_required_before_real_data: true,
  },
};

describe("RoiPage — 정상 시나리오(happy path)", () => {
  it("낙관/기준/보수 3개 시나리오와 공개사항을 렌더링한다", async () => {
    mockGetRoi.mockResolvedValue(roiResponse);

    render(<RoiPage />);

    expect(await screen.findByText("낙관")).toBeInTheDocument();
    expect(screen.getByText("기준")).toBeInTheDocument();
    expect(screen.getByText("보수")).toBeInTheDocument();
    // 세 시나리오 모두 fixture상 annual_defendable_expected_loss가 같은 값(500.0억원)이라 여러 개 나온다
    expect(screen.getAllByText("500.0억원").length).toBeGreaterThan(0);
    expect(screen.getByText(/12일/)).toBeInTheDocument();
    expect(screen.getByText(/공개 통계 원문과 기준연도는 연결되어 있지 않습니다/)).toBeInTheDocument();
  });
});

describe("RoiPage — 로딩 상태", () => {
  it("응답이 오기 전에는 로딩 문구를 표시한다", () => {
    mockGetRoi.mockReturnValue(new Promise(() => {}));
    render(<RoiPage />);
    expect(screen.getByText(/불러오는 중/)).toBeInTheDocument();
  });
});

describe("RoiPage — 예외 케이스", () => {
  it("조회가 실패하면 에러 메시지를 표시한다", async () => {
    mockGetRoi.mockRejectedValue(new Error("서버 오류"));
    render(<RoiPage />);
    expect(await screen.findByText(/불러오지 못했습니다/)).toBeInTheDocument();
  });
});

describe("RoiPage — 경계값(회수기간 계산 불가)", () => {
  it("payback_period_days가 null이면 payback_note를 표시한다", async () => {
    mockGetRoi.mockResolvedValue({
      ...roiResponse,
      scenarios: {
        ...roiResponse.scenarios,
        보수: scenario({
          payback_period_days: null,
          payback_note: "연간 실현 절감액이 0이어서 투자 회수기간을 계산할 수 없음",
        }),
      },
    });

    render(<RoiPage />);

    expect(await screen.findByText(/투자 회수기간을 계산할 수 없음/)).toBeInTheDocument();
  });
});
