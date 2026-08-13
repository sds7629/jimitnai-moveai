import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReviewedCandidatesTable } from "../ReviewedCandidatesTable";
import type { CandidatesReviewedSection } from "../../types";

const section: CandidatesReviewedSection = {
  total_count: 3,
  excluded_count: 2,
  candidates: [
    {
      candidate_id: 1,
      candidate_type: "baseline",
      description: "현행 유지",
      start_time_variant: null,
      validation_status: "가능",
      exclusion_category: null,
      exclusion_detail: null,
      preconditions: [],
    },
    {
      candidate_id: 2,
      candidate_type: "대체선사",
      description: "타 선사 선복 확보",
      start_time_variant: "D+1",
      validation_status: "조건부",
      exclusion_category: null,
      exclusion_detail: null,
      preconditions: ["선복 여유 확인", "운임 재협상"],
    },
    {
      candidate_id: 3,
      candidate_type: "항공전환",
      description: "항공 화물 전환",
      start_time_variant: null,
      validation_status: "불가능",
      exclusion_category: "예산초과",
      exclusion_detail: "항공 운임이 승인 한도를 초과",
      preconditions: [],
    },
  ],
};

describe("ReviewedCandidatesTable — 정상 시나리오(happy path)", () => {
  it("후보 유형·설명·검증 상태·제외 사유·선행 조건을 모두 표로 렌더링한다", () => {
    render(<ReviewedCandidatesTable section={section} />);

    expect(screen.getByText("대체선사")).toBeInTheDocument();
    expect(screen.getByText("타 선사 선복 확보")).toBeInTheDocument();
    expect(screen.getByText("조건부")).toBeInTheDocument();
    expect(screen.getByText("선복 여유 확인, 운임 재협상")).toBeInTheDocument();
    expect(screen.getByText(/예산초과.*항공 운임이 승인 한도를 초과/)).toBeInTheDocument();
  });

  it("total_count와 excluded_count를 요약 문구로 표시한다", () => {
    render(<ReviewedCandidatesTable section={section} />);

    expect(screen.getByText(/검토 3건/)).toBeInTheDocument();
    expect(screen.getByText(/제외 2건/)).toBeInTheDocument();
  });

  it("검증 상태별로 서로 다른 색상 뱃지를 사용한다", () => {
    render(<ReviewedCandidatesTable section={section} />);

    expect(screen.getByText("가능").className).toContain("--teal");
    expect(screen.getByText("조건부").className).toContain("--amber");
    expect(screen.getByText("불가능").className).toContain("--red");
  });
});

describe("ReviewedCandidatesTable — 경계값(제외 사유·선행 조건 없음)", () => {
  it("exclusion_category와 preconditions가 비어 있으면 '-'로 표시한다", () => {
    render(<ReviewedCandidatesTable section={section} />);

    // 1번 후보는 제외 사유·선행 조건이 모두 없어서 '-'가 2개 이상 나온다
    expect(screen.getAllByText("-").length).toBeGreaterThanOrEqual(2);
  });

  it("검증되지 않은 후보는 중립 색상 뱃지로 표시한다", () => {
    const unvalidated: CandidatesReviewedSection = {
      total_count: 1,
      excluded_count: 1,
      candidates: [
        {
          candidate_id: 9,
          candidate_type: "미검증안",
          description: "아직 검증 전",
          start_time_variant: null,
          validation_status: "미검증",
          exclusion_category: null,
          exclusion_detail: null,
          preconditions: [],
        },
      ],
    };

    render(<ReviewedCandidatesTable section={unvalidated} />);

    expect(screen.getByText("미검증").className).toContain("--text-secondary");
  });

  it("exclusion_category만 있고 detail이 null이면 카테고리만 표시한다", () => {
    const detailless: CandidatesReviewedSection = {
      total_count: 1,
      excluded_count: 1,
      candidates: [
        {
          candidate_id: 8,
          candidate_type: "육상전환",
          description: "육상 운송 전환",
          start_time_variant: null,
          validation_status: "불가능",
          exclusion_category: "기한불가",
          exclusion_detail: null,
          preconditions: [],
        },
      ],
    };

    render(<ReviewedCandidatesTable section={detailless} />);

    expect(screen.getByText("기한불가")).toBeInTheDocument();
  });
});

describe("ReviewedCandidatesTable — 실패 시나리오(후보 없음)", () => {
  it("candidates가 빈 배열이면 안내 문구를 표시한다", () => {
    const empty: CandidatesReviewedSection = { total_count: 0, excluded_count: 0, candidates: [] };

    render(<ReviewedCandidatesTable section={empty} />);

    expect(screen.getByText("검토한 대응안이 없습니다.")).toBeInTheDocument();
  });

  it("후보가 없으면 표 헤더도 렌더링하지 않는다", () => {
    const empty: CandidatesReviewedSection = { total_count: 0, excluded_count: 0, candidates: [] };

    render(<ReviewedCandidatesTable section={empty} />);

    expect(screen.queryByText("검증 상태")).not.toBeInTheDocument();
  });
});
