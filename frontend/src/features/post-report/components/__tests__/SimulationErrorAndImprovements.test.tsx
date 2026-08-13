import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SimulationErrorAndImprovements } from "../SimulationErrorAndImprovements";
import type { FutureImprovementsSection, SimulationErrorSection } from "../../types";

const simulationError: SimulationErrorSection = {
  error_calculable: false,
  reason: "실적 데이터를 입력받는 메커니즘이 없어 시뮬레이션 오차를 계산할 수 없습니다.",
  candidates: [
    {
      candidate_id: 1,
      candidate_type: "대체선사",
      confidence: 0.82,
      sensitivity_variables: ["운임", "선복 여유"],
      assumption: { 날씨: "양호", 물량: 120 },
      data_version: "v3",
      scenario_version: "s2",
      calculated_at: "2026-08-01T10:00:00Z",
    },
    {
      candidate_id: 2,
      candidate_type: "항공전환",
      confidence: null,
      sensitivity_variables: [],
      assumption: {},
      data_version: "v3",
      scenario_version: "s2",
      calculated_at: "2026-08-02T10:00:00Z",
    },
  ],
};

const improvements: FutureImprovementsSection = [
  {
    category: "실적 확정 데이터 입력 메커니즘 부재",
    description: "실적 입력 API가 없어 사후보고서가 영구히 잠정 상태로 남습니다.",
  },
  {
    category: "실행 편차 감지 휴리스틱의 한계",
    description: "5개 편차 조건 중 2개만 판단합니다.",
  },
  {
    category: "비용 귀속 휴리스틱의 법적 한계",
    description: "법무 검토를 대체하지 않습니다.",
  },
];

describe("SimulationErrorAndImprovements — 섹션 10 시뮬레이션 오차(정상 시나리오)", () => {
  it("reason 문구를 안내 박스로 렌더링한다", () => {
    render(<SimulationErrorAndImprovements simulationError={simulationError} improvements={improvements} />);

    expect(
      screen.getByText("실적 데이터를 입력받는 메커니즘이 없어 시뮬레이션 오차를 계산할 수 없습니다.")
    ).toBeInTheDocument();
  });

  it("candidates 여러 건의 confidence(%)와 sensitivity_variables를 렌더링한다", () => {
    render(<SimulationErrorAndImprovements simulationError={simulationError} improvements={improvements} />);

    expect(screen.getByText("대체선사")).toBeInTheDocument();
    expect(screen.getByText(/82%/)).toBeInTheDocument();
    expect(screen.getByText("운임")).toBeInTheDocument();
    expect(screen.getByText("선복 여유")).toBeInTheDocument();
  });
});

describe("SimulationErrorAndImprovements — 섹션 10 경계값/예외", () => {
  it("candidates가 빈 배열이면 안내 문구를 표시한다", () => {
    const empty: SimulationErrorSection = { ...simulationError, candidates: [] };

    render(<SimulationErrorAndImprovements simulationError={empty} improvements={improvements} />);

    expect(screen.getByText("시뮬레이션 결과가 있는 후보가 없습니다.")).toBeInTheDocument();
  });

  it("confidence가 null인 후보는 %로 표시하지 않는다", () => {
    render(<SimulationErrorAndImprovements simulationError={simulationError} improvements={improvements} />);

    expect(screen.getByText("항공전환")).toBeInTheDocument();
    expect(screen.queryByText(/신뢰도 null/)).not.toBeInTheDocument();
    // 82%는 대체선사 카드에만 존재해야 하고, 전체 문서에 %가 정확히 1건만 나온다
    expect(screen.getAllByText(/%$/).length).toBe(1);
  });
});

describe("SimulationErrorAndImprovements — 섹션 12 향후 개선사항(정상 시나리오)", () => {
  it("여러 항목을 category/description으로 렌더링한다", () => {
    render(<SimulationErrorAndImprovements simulationError={simulationError} improvements={improvements} />);

    expect(screen.getByText("실적 확정 데이터 입력 메커니즘 부재")).toBeInTheDocument();
    expect(screen.getByText("실적 입력 API가 없어 사후보고서가 영구히 잠정 상태로 남습니다.")).toBeInTheDocument();
    expect(screen.getByText("실행 편차 감지 휴리스틱의 한계")).toBeInTheDocument();
    expect(screen.getByText("비용 귀속 휴리스틱의 법적 한계")).toBeInTheDocument();
  });

  it("category별로 서로 다른 항목이 구분되어 렌더링된다", () => {
    render(<SimulationErrorAndImprovements simulationError={simulationError} improvements={improvements} />);

    expect(screen.getByText("5개 편차 조건 중 2개만 판단합니다.")).toBeInTheDocument();
    expect(screen.getByText("법무 검토를 대체하지 않습니다.")).toBeInTheDocument();
  });
});

describe("SimulationErrorAndImprovements — 섹션 12 실패 시나리오(개선사항 없음)", () => {
  it("improvements가 빈 배열이면 안내 문구를 표시한다", () => {
    render(<SimulationErrorAndImprovements simulationError={simulationError} improvements={[]} />);

    expect(screen.getByText("개선사항 없음.")).toBeInTheDocument();
  });
});
