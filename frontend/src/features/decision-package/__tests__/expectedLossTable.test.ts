import { describe, expect, it } from "vitest";
import { buildExpectedLossTable } from "../expectedLossTable";
import type { ConfidenceAndUncertaintySection, ExpectedLossP90CvarSection } from "../types";

describe("buildExpectedLossTable — 정상 시나리오(happy path)", () => {
  it("두 섹션을 candidate id 기준으로 합쳐 표 행을 만든다", () => {
    const expectedLossSection: ExpectedLossP90CvarSection = {
      "1": {
        candidate_type: "안전재고 사전 당김",
        description: "설명",
        expected_loss: 100_000_000,
        p90: 150_000_000,
        cvar: 180_000_000,
      },
    };
    const confidenceSection: ConfidenceAndUncertaintySection = {
      "1": {
        confidence: 0.78,
        uncertainty_range: {
          expected_loss: 100_000_000,
          p90: 150_000_000,
          cvar: 180_000_000,
          p90_minus_expected_loss: 50_000_000,
          cvar_minus_p90: 30_000_000,
        },
      },
    };

    const rows = buildExpectedLossTable(expectedLossSection, confidenceSection);

    expect(rows).toEqual([
      {
        candidateId: "1",
        candidateType: "안전재고 사전 당김",
        description: "설명",
        expectedLoss: "1.0억원",
        p90: "1.5억원",
        cvar: "1.8억원",
        confidencePercent: 78,
        p90MinusExpectedLoss: "0.5억원",
        cvarMinusP90: "0.3억원",
      },
    ]);
  });
});

describe("buildExpectedLossTable — 경계값", () => {
  it("두 섹션 다 비어있으면 빈 배열을 반환한다", () => {
    expect(buildExpectedLossTable({}, {})).toEqual([]);
  });

  it("confidence_and_uncertainty에 짝이 없는 후보는 confidence/불확실성 값이 null로 채워진다", () => {
    const expectedLossSection: ExpectedLossP90CvarSection = {
      "2": { candidate_type: "긴급 항공 전환", description: "d", expected_loss: 50_000_000, p90: null, cvar: null },
    };

    const rows = buildExpectedLossTable(expectedLossSection, {});

    expect(rows[0]).toEqual({
      candidateId: "2",
      candidateType: "긴급 항공 전환",
      description: "d",
      expectedLoss: "0.5억원",
      p90: "-",
      cvar: "-",
      confidencePercent: null,
      p90MinusExpectedLoss: "-",
      cvarMinusP90: "-",
    });
  });
});
