import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SopPanel } from "../SopPanel";
import { strikeScenarioMock } from "../../mockData";
import type { MatchedSop } from "../../types";

describe("SopPanel — 정상 시나리오(steps가 채워진 항목 펼치기/접기)", () => {
  it("steps가 채워진 SOP는 기본으로 펼쳐져 있고, 클릭하면 접히고 다시 클릭하면 펼쳐진다", async () => {
    const user = userEvent.setup();
    render(<SopPanel sops={strikeScenarioMock.sops} matchedCount={strikeScenarioMock.matchedSopCount} showDemoNote={false} />);

    // SOP-AIR-02는 mockData 버그 수정으로 steps가 채워져 기본으로 펼쳐져 있어야 한다
    expect(screen.getByText(/항공 포워더 3개사 이상에 가용 스케줄ㆍ운임 견적 동시 요청/)).toBeInTheDocument();

    const airSopHeader = screen.getByText(/SOP-AIR-02/).closest("div")!;
    await user.click(airSopHeader);
    expect(screen.queryByText(/항공 포워더 3개사 이상에 가용 스케줄ㆍ운임 견적 동시 요청/)).not.toBeInTheDocument();

    await user.click(airSopHeader);
    expect(screen.getByText(/항공 포워더 3개사 이상에 가용 스케줄ㆍ운임 견적 동시 요청/)).toBeInTheDocument();
  });
});

describe("SopPanel — mockData 회귀 테스트(6건 전체 steps 보유)", () => {
  it("strikeScenarioMock.sops의 6개 항목 모두 steps와 reference가 채워져 있다", () => {
    expect(strikeScenarioMock.sops).toHaveLength(6);
    strikeScenarioMock.sops.forEach((sop: MatchedSop) => {
      expect(sop.steps).toBeDefined();
      expect(sop.steps!.length).toBeGreaterThanOrEqual(3);
      expect(sop.reference).toBeTruthy();
    });
  });

  it("matchedSopCount와 실제 sops 배열 길이가 일치한다", () => {
    expect(strikeScenarioMock.matchedSopCount).toBe(strikeScenarioMock.sops.length);
  });
});

describe("SopPanel — 경계값(steps가 없는 항목은 여전히 비인터랙티브)", () => {
  it("steps가 없는 SOP는 화살표가 항상 ▸이고 클릭해도 펼쳐지지 않는다", async () => {
    const user = userEvent.setup();
    const staticOnlySop: MatchedSop = { code: "SOP-STATIC-00", title: "정적 SOP", owningTeam: "테스트팀" };
    render(<SopPanel sops={[staticOnlySop]} matchedCount={1} showDemoNote={false} />);

    expect(screen.getByText("▸")).toBeInTheDocument();

    const header = screen.getByText(/SOP-STATIC-00/).closest("div")!;
    await user.click(header);
    // 펼칠 절차 목록이 없으므로 클릭 후에도 여전히 접힘 화살표(▸)만 존재한다
    expect(screen.getByText("▸")).toBeInTheDocument();
    expect(screen.queryByText("▾")).not.toBeInTheDocument();
  });
});

describe("SopPanel — 헤더 매칭 건수 표시", () => {
  it("matchedCount prop 값을 '{count}건 매칭' 형태로 표시한다", () => {
    render(<SopPanel sops={strikeScenarioMock.sops} matchedCount={6} showDemoNote={false} />);
    expect(screen.getByText("6건 매칭")).toBeInTheDocument();
  });
});
