import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { LossSettlementCard } from "../LossSettlementCard";
import type { AvoidedLossSection, CostAttributionApi, ExpectedVsActualLossSection } from "../../types";

const SCOPE_NOTE = "이 시스템에는 실적 확정값(실측 손실, 실제 완료 시각 등)을 입력받는 API가 없습니다";

const loss: ExpectedVsActualLossSection = {
  expected_loss: {
    baseline: {
      available: true,
      candidate_id: 1,
      candidate_type: "무대응",
      description: "아무 조치도 하지 않음",
      start_time_variant: null,
      simulation: {
        available: true,
        expected_loss: 99_610_000_000,
        p90: 120_000_000_000,
        cvar: 130_000_000_000,
        confidence: 0.8,
        data_version: "d1",
        scenario_version: "s1",
        calculated_at: "2026-08-10T01:00:00Z",
      },
    },
    approved_candidate: {
      available: true,
      candidate_id: 4,
      candidate_type: "대체 항만",
      description: "광양항으로 우회",
      start_time_variant: "now",
      simulation: {
        available: true,
        expected_loss: 56_460_000_000,
        p90: 70_000_000_000,
        cvar: 80_000_000_000,
        confidence: 0.71,
        data_version: "d2",
        scenario_version: "s2",
        calculated_at: "2026-08-11T01:00:00Z",
      },
    },
  },
  actual_status: "미확정",
  actual_loss: { available: false, reason: SCOPE_NOTE },
};

const avoidedLossAvailable: AvoidedLossSection = {
  expected_avoided_loss: {
    available: true,
    amount: 43_150_000_000,
    baseline: {
      candidate_id: 1,
      candidate_type: "무대응",
      description: "아무 조치도 하지 않음",
      expected_loss: 99_610_000_000,
      data_version: "d1",
      scenario_version: "s1",
      calculated_at: "2026-08-10T01:00:00Z",
      has_simulation_result: true,
    },
    approved: {
      candidate_id: 4,
      candidate_type: "대체 항만",
      description: "광양항으로 우회",
      expected_loss: 56_460_000_000,
      data_version: "d2",
      scenario_version: "s2",
      calculated_at: "2026-08-11T01:00:00Z",
      has_simulation_result: true,
    },
    reason: null,
    note: "예상 회피손실 = baseline 후보의 기대손실 - 승인된 후보의 기대손실. 실측 손실 데이터가 없어 추정치입니다.",
  },
  additional_cost_incurred: {
    available: false,
    reason: "실적 비용 확정 데이터를 입력받는 메커니즘이 이 시스템에 없어 추가 발생 비용을 산출할 수 없습니다.",
  },
};

const costAttribution: CostAttributionApi = {
  incident_id: 1,
  is_heuristic: true,
  rag_unavailable: false,
  heuristic_disclaimer: "이 분류는 실제 법무 판단이 아니라 계약 조항 RAG 검색 결과에 기반한 휴리스틱입니다.",
  avoided_loss_basis: {},
  matched_ld_clauses: [{ chunk_id: 1 }, { chunk_id: 2 }],
  matched_dnd_clauses: [{ chunk_id: 3 }],
  breakdown: { 직접_손익_효과: 0, 고객_회피비용: 0, 분쟁_협상_가능_금액: 43_150_000_000 },
  classification_note: "계약 조항 검색 결과 LD 관련 조항이 발견됨",
};

describe("LossSettlementCard — 섹션 7(예상 손실과 실제 손실)", () => {
  it("baseline·승인후보 예상손실 숫자를 억원 단위로 비교 표시한다(happy path)", () => {
    render(<LossSettlementCard loss={loss} avoidedLoss={avoidedLossAvailable} costAttribution={costAttribution} />);

    expect(screen.getByText("996.1억원")).toBeInTheDocument();
    expect(screen.getByText("564.6억원")).toBeInTheDocument();
  });

  it("실제 손실은 미확정 상태와 사유 문구를 그대로 노출한다(happy path)", () => {
    render(<LossSettlementCard loss={loss} avoidedLoss={avoidedLossAvailable} costAttribution={costAttribution} />);

    expect(screen.getByText(/실제 손실: 미확정/)).toBeInTheDocument();
    expect(screen.getByText(/실적 확정값.*입력받는 API가 없습니다/)).toBeInTheDocument();
  });

  it("baseline 또는 승인후보가 available:false면 '-'로 표시한다(경계값)", () => {
    const noApproved: ExpectedVsActualLossSection = {
      ...loss,
      expected_loss: {
        baseline: loss.expected_loss.baseline,
        approved_candidate: { available: false },
      },
    };

    const { container } = render(
      <LossSettlementCard loss={noApproved} avoidedLoss={avoidedLossAvailable} costAttribution={costAttribution} />,
    );

    expect(container).toHaveTextContent("승인후보 -");
    expect(screen.getByText("996.1억원")).toBeInTheDocument();
  });
});

describe("LossSettlementCard — 섹션 8(회피한 손실과 추가 발생 비용)", () => {
  it("available:true면 회피 추정액과 note 문구를 렌더링한다(happy path)", () => {
    render(<LossSettlementCard loss={loss} avoidedLoss={avoidedLossAvailable} costAttribution={costAttribution} />);

    expect(screen.getByText("431.5억원")).toBeInTheDocument();
    expect(screen.getByText(/예상 회피손실 = baseline 후보의 기대손실/)).toBeInTheDocument();
  });

  it("available:false면 reason을 안내 박스로 표시한다(edge/실패)", () => {
    const unavailableAvoided: AvoidedLossSection = {
      expected_avoided_loss: {
        available: false,
        amount: null,
        baseline: null,
        approved: null,
        reason: "baseline 후보(response_candidates.candidate_type='baseline')가 없음",
      },
      additional_cost_incurred: avoidedLossAvailable.additional_cost_incurred,
    };

    render(<LossSettlementCard loss={loss} avoidedLoss={unavailableAvoided} costAttribution={costAttribution} />);

    expect(screen.getByText(/baseline 후보.*가 없음/)).toBeInTheDocument();
    expect(screen.queryByText("431.5억원")).not.toBeInTheDocument();
  });

  it("additional_cost_incurred.reason을 안내 박스로 표시한다", () => {
    render(<LossSettlementCard loss={loss} avoidedLoss={avoidedLossAvailable} costAttribution={costAttribution} />);

    expect(screen.getByText(/추가 발생 비용:.*실적 비용 확정 데이터/)).toBeInTheDocument();
  });
});

describe("LossSettlementCard — 섹션 9(LD·D&D 귀책 및 비용 부담 주체, 비용귀속 카드와 중복 방지)", () => {
  it("matched_ld_clauses/matched_dnd_clauses 건수를 뱃지로 표시한다(happy path)", () => {
    render(<LossSettlementCard loss={loss} avoidedLoss={avoidedLossAvailable} costAttribution={costAttribution} />);

    expect(screen.getByText("LD 조항 매칭 2건")).toBeInTheDocument();
    expect(screen.getByText("D&D 조항 매칭 1건")).toBeInTheDocument();
  });

  it("두 조항 모두 0건이면 0건으로 표시한다(경계값)", () => {
    const noMatches: CostAttributionApi = { ...costAttribution, matched_ld_clauses: [], matched_dnd_clauses: [] };

    render(<LossSettlementCard loss={loss} avoidedLoss={avoidedLossAvailable} costAttribution={noMatches} />);

    expect(screen.getByText("LD 조항 매칭 0건")).toBeInTheDocument();
    expect(screen.getByText("D&D 조항 매칭 0건")).toBeInTheDocument();
  });

  it("breakdown 금액 문자열이나 heuristic_disclaimer 원문은 이 컴포넌트 안에 렌더링하지 않는다(중복 방지 회귀 테스트)", () => {
    render(<LossSettlementCard loss={loss} avoidedLoss={avoidedLossAvailable} costAttribution={costAttribution} />);

    // 비용 귀속 카드가 이미 렌더링하는 값들 — breakdown 금액(분쟁_협상_가능_금액=431.5억원은
    // 회피 추정액과 우연히 같은 금액이므로 disclaimer/classification_note 원문으로 중복 여부를 확인한다
    expect(screen.queryByText(costAttribution.heuristic_disclaimer)).not.toBeInTheDocument();
    expect(screen.queryByText(costAttribution.classification_note)).not.toBeInTheDocument();
    expect(screen.queryByText(/휴리스틱/)).not.toBeInTheDocument();
    expect(screen.getByText(/상세 금액 분류는 위 비용 귀속 카드 참고/)).toBeInTheDocument();
  });
});
