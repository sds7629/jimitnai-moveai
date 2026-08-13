import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { OverviewAndDecisionCard } from "../OverviewAndDecisionCard";
import type { FinalDecisionSection, OverviewSection } from "../../types";

const overview: OverviewSection = {
  incident_id: 1,
  type: "항만 파업",
  location: "부산항",
  occurred_at: "2026-08-10T00:00:00Z",
  status: "진행중",
  duplicate_of_incident_id: null,
  affected_targets: { 공장: ["A공장"] },
  assumptions_at_intake: ["항만 재개방 시점 미확정"],
  created_at: "2026-08-10T00:10:00Z",
};

describe("OverviewAndDecisionCard — 정상 시나리오(happy path)", () => {
  it("사건 개요와 최종 결정을 함께 표시한다", () => {
    const decision: FinalDecisionSection = {
      approvals_history: [
        {
          approval_id: 1,
          decision_type: "승인",
          reason: "손실 최소화",
          approver: "김담당",
          decided_at: "2026-08-11T00:00:00Z",
          data_version_ref: "v1",
          scenario_version_ref: "s1",
        },
      ],
      final_decision: {
        available: true,
        approval_id: 1,
        decision_type: "승인",
        reason: "손실 최소화",
        approver: "김담당",
        decided_at: "2026-08-11T00:00:00Z",
        data_version_ref: "v1",
        scenario_version_ref: "s1",
      },
    };

    render(<OverviewAndDecisionCard overview={overview} decision={decision} />);

    expect(screen.getByText("항만 파업")).toBeInTheDocument();
    expect(screen.getByText("부산항")).toBeInTheDocument();
    expect(screen.getByText("항만 재개방 시점 미확정")).toBeInTheDocument();
    expect(screen.getByText(/김담당/)).toBeInTheDocument();
    expect(screen.getByText(/손실 최소화/)).toBeInTheDocument();
  });
});

describe("OverviewAndDecisionCard — 경계값(승인 이력 없음)", () => {
  it("최종 결정이 없으면 사유를 표시한다", () => {
    const decision: FinalDecisionSection = {
      approvals_history: [],
      final_decision: { available: false, reason: "이 사건에 대한 승인/반려 이력(approvals)이 없음" },
    };

    render(<OverviewAndDecisionCard overview={overview} decision={decision} />);

    expect(screen.getByText(/승인\/반려 이력/)).toBeInTheDocument();
  });
});

describe("OverviewAndDecisionCard — 실패 시나리오(영향 대상·가정 없음)", () => {
  it("affected_targets와 assumptions_at_intake가 비어 있어도 오류 없이 렌더링된다", () => {
    const emptyOverview: OverviewSection = { ...overview, affected_targets: {}, assumptions_at_intake: [] };
    const decision: FinalDecisionSection = {
      approvals_history: [],
      final_decision: { available: false, reason: "이력 없음" },
    };

    render(<OverviewAndDecisionCard overview={emptyOverview} decision={decision} />);

    expect(screen.getByText("등록된 가정이 없습니다.")).toBeInTheDocument();
  });
});
