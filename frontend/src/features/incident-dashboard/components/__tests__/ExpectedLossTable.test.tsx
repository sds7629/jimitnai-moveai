import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ExpectedLossTable } from "../ExpectedLossTable";
import type { ExpectedLossTableRow } from "../../../decision-package/expectedLossTable";

function row(overrides: Partial<ExpectedLossTableRow> = {}): ExpectedLossTableRow {
  return {
    candidateId: "1",
    candidateType: "안전재고 사전 당김",
    description: "설명",
    expectedLoss: "1.0억원",
    p90: "1.5억원",
    cvar: "1.8억원",
    confidencePercent: 78,
    p90MinusExpectedLoss: "0.5억원",
    cvarMinusP90: "0.3억원",
    ...overrides,
  };
}

describe("ExpectedLossTable — 정상 시나리오(happy path)", () => {
  it("후보별 기대손실·P90·CVaR·신뢰도를 표로 렌더링한다", () => {
    render(<ExpectedLossTable rows={[row()]} />);

    expect(screen.getByText("안전재고 사전 당김")).toBeInTheDocument();
    expect(screen.getByText("1.0억원")).toBeInTheDocument();
    expect(screen.getByText("1.5억원")).toBeInTheDocument();
    expect(screen.getByText("1.8억원")).toBeInTheDocument();
    expect(screen.getByText("78%")).toBeInTheDocument();
  });
});

describe("ExpectedLossTable — 경계값", () => {
  it("confidencePercent가 null이면 '-'를 표시한다", () => {
    render(<ExpectedLossTable rows={[row({ confidencePercent: null })]} />);
    expect(screen.getByText("안전재고 사전 당김").closest("tr")).toHaveTextContent("-");
  });

  it("행이 없으면 안내 문구를 표시한다", () => {
    render(<ExpectedLossTable rows={[]} />);
    expect(screen.getByText(/시뮬레이션된 후보가 없습니다/)).toBeInTheDocument();
  });
});
