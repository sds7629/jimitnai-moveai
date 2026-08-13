import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { NowVs6hComparison } from "../NowVs6hComparison";
import type { NowVs6hVsNoActionSection, PairSummaryApi } from "../../../decision-package/types";

function pair(overrides: Partial<PairSummaryApi> = {}): PairSummaryApi {
  return {
    candidate_id: 1,
    candidate_type: "안전재고 사전 당김",
    description: "설명",
    start_time_variant: "now",
    expected_loss: 100_000_000,
    p90: 150_000_000,
    cvar: 180_000_000,
    ...overrides,
  };
}

describe("NowVs6hComparison — 정상 시나리오(happy path)", () => {
  it("무대응/지금/6시간후 3장을 카드로 렌더링한다", () => {
    const section: NowVs6hVsNoActionSection = {
      no_action: pair({ candidate_id: 1, candidate_type: "baseline", expected_loss: 200_000_000 }),
      now: pair({ candidate_id: 2, candidate_type: "안전재고 사전 당김" }),
      plus_6h: pair({ candidate_id: 3, candidate_type: "긴급 항공 전환", expected_loss: 130_000_000 }),
    };

    render(<NowVs6hComparison section={section} />);

    expect(screen.getByText("무대응")).toBeInTheDocument();
    expect(screen.getByText("지금 대응")).toBeInTheDocument();
    expect(screen.getByText("6시간 후 대응")).toBeInTheDocument();
    expect(screen.getByText("baseline")).toBeInTheDocument();
    expect(screen.getByText("안전재고 사전 당김")).toBeInTheDocument();
    expect(screen.getByText("긴급 항공 전환")).toBeInTheDocument();
    expect(screen.getByText("2.0억원")).toBeInTheDocument();
  });
});

describe("NowVs6hComparison — 경계값(해당 후보 없음)", () => {
  it("슬롯이 null이면 '해당 후보 없음'을 표시한다", () => {
    const section: NowVs6hVsNoActionSection = { no_action: pair(), now: null, plus_6h: null };
    render(<NowVs6hComparison section={section} />);

    expect(screen.getAllByText(/해당 후보 없음/)).toHaveLength(2);
  });

  it("섹션 객체에 슬롯 키 자체가 없어도(undefined) 오류 없이 '해당 후보 없음'을 표시한다", () => {
    // 백엔드 blob이 loosely-typed dict라 키가 아예 빠진 상태({})로 올 수도 있다 — null과 동일하게 처리
    render(<NowVs6hComparison section={{} as NowVs6hVsNoActionSection} />);
    expect(screen.getAllByText(/해당 후보 없음/)).toHaveLength(3);
  });
});
