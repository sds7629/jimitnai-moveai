import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RankedCandidatesList } from "../RankedCandidatesList";
import type { RankedCandidatesSection } from "../../../decision-package/types";

describe("RankedCandidatesList — 정상 시나리오(happy path)", () => {
  it("순위·composite score 순으로 후보를 렌더링한다", () => {
    const section: RankedCandidatesSection = {
      ranked: [
        {
          candidate_id: 1,
          candidate_type: "baseline",
          description: "무대응",
          start_time_variant: null,
          validation_status: "가능",
          preconditions: [],
          expected_loss: 200_000_000,
          p90: 250_000_000,
          cvar: 300_000_000,
          risk_score: 235_000_000,
          feasibility_penalty: 0,
          composite_score: 235_000_000,
          rank: 1,
        },
        {
          candidate_id: 2,
          candidate_type: "안전재고 사전 당김",
          description: "설명",
          start_time_variant: "now",
          validation_status: "조건부",
          preconditions: ["창고 여유 확보"],
          expected_loss: 100_000_000,
          p90: 150_000_000,
          cvar: 180_000_000,
          risk_score: 122_000_000,
          feasibility_penalty: 0.2,
          composite_score: 146_400_000,
          rank: 2,
        },
      ],
      excluded_from_ranking: [],
    };

    render(<RankedCandidatesList section={section} />);

    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("baseline")).toBeInTheDocument();
    expect(screen.getByText("안전재고 사전 당김")).toBeInTheDocument();
    expect(screen.getByText(/창고 여유 확보/)).toBeInTheDocument();
  });
});

describe("RankedCandidatesList — 경계값(제외된 후보 있음)", () => {
  it("excluded_from_ranking을 별도 목록으로 사유와 함께 표시한다", () => {
    const section: RankedCandidatesSection = {
      ranked: [],
      excluded_from_ranking: [
        {
          candidate_id: 3,
          candidate_type: "긴급 항공 전환",
          description: "설명",
          validation_status: "불가능",
          exclusion_category: "예산초과",
          exclusion_detail: "항공 예산 한도 초과",
          reason: "시뮬레이션 결과가 없어 최적화/순위화 대상에서 제외됨",
        },
      ],
    };

    render(<RankedCandidatesList section={section} />);

    expect(screen.getByText("긴급 항공 전환")).toBeInTheDocument();
    expect(screen.getByText(/시뮬레이션 결과가 없어/)).toBeInTheDocument();
  });
});

describe("RankedCandidatesList — 실패 시나리오(둘 다 비어 있음)", () => {
  it("순위 후보도 제외 후보도 없으면 안내 문구를 표시한다", () => {
    render(<RankedCandidatesList section={{ ranked: [], excluded_from_ranking: [] }} />);
    expect(screen.getByText("순위화된 후보가 없습니다.")).toBeInTheDocument();
  });
});
