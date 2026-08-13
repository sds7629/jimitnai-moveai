import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { FeasibilityTable } from "../FeasibilityTable";
import type { FeasibilityTableRow } from "../../../decision-package/feasibilityTable";

describe("FeasibilityTable — 정상 시나리오(happy path)", () => {
  it("검증 상태·제외 사유·민감도 변수를 표로 렌더링한다", () => {
    const rows: FeasibilityTableRow[] = [
      {
        candidateId: "1",
        validationStatus: "가능",
        exclusionCategory: null,
        exclusionDetail: null,
        preconditions: ["창고 여유 확보"],
        sensitivityVariables: ["항만 재개방 시점"],
      },
    ];

    render(<FeasibilityTable rows={rows} />);

    expect(screen.getByText("가능")).toBeInTheDocument();
    expect(screen.getByText("창고 여유 확보")).toBeInTheDocument();
    expect(screen.getByText("항만 재개방 시점")).toBeInTheDocument();
  });
});

describe("FeasibilityTable — 경계값(제외된 후보)", () => {
  it("불가능 판정 후보는 제외 카테고리·상세 사유를 표시한다", () => {
    const rows: FeasibilityTableRow[] = [
      {
        candidateId: "2",
        validationStatus: "불가능",
        exclusionCategory: "자원부족",
        exclusionDetail: "가용 창고 없음",
        preconditions: [],
        sensitivityVariables: [],
      },
    ];

    render(<FeasibilityTable rows={rows} />);

    expect(screen.getByText("불가능")).toBeInTheDocument();
    expect(screen.getByText(/자원부족/)).toBeInTheDocument();
    expect(screen.getByText(/가용 창고 없음/)).toBeInTheDocument();
  });
});

describe("FeasibilityTable — 실패 시나리오(빈 목록)", () => {
  it("행이 없으면 안내 문구를 표시한다", () => {
    render(<FeasibilityTable rows={[]} />);
    expect(screen.getByText("검증된 후보가 없습니다.")).toBeInTheDocument();
  });
});
