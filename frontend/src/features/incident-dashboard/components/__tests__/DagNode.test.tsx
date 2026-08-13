import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DagNode } from "../DagNode";
import type { ImpactDagNode } from "../../types";

const nodeWithDetail: ImpactDagNode = {
  id: "transport-pctc",
  entityType: "transport",
  label: "PCTC 해상운송 부산→유럽",
  delayDays: 4.5,
  detail: {
    basis: "선사 스케줄 공지, 항구 혼잡도 지표",
    uncertainty: "medium",
    responsibleParty: "해상운송팀",
    affectedTarget: "PCTC 부산→유럽 항로",
    expectedTime: "2026-08-15T09:00:00Z",
  },
};

const nodeWithoutDetail: ImpactDagNode = {
  id: "line-asan",
  entityType: "production_line",
  label: "아산 라인",
};

// jsdom에서는 실제 CSS 트랜지션 진행 상태를 검증할 수 없으므로, grid-rows 트릭이 올바른 CSS 클래스를
// 토글하는지와 콘텐츠가 항상 DOM에 남아있는지(조건부 마운트가 아님)를 검증한다.
describe("DagNode — detail이 있는 노드는 항상 DOM에 상세 콘텐츠를 유지한다", () => {
  it("detailOpen 기본값(true)에서 상세 콘텐츠(근거/책임 주체 등)가 렌더링된다", () => {
    render(<DagNode node={nodeWithDetail} />);

    expect(screen.getByText(/불확실성: medium/)).toBeInTheDocument();
    expect(screen.getByText(/해상운송팀/)).toBeInTheDocument();
    expect(screen.getByText(/PCTC 부산→유럽 항로/)).toBeInTheDocument();
  });
});

describe("DagNode — 클릭 시 grid-rows 클래스 토글(펼치기/접기 애니메이션)", () => {
  it("클릭할 때마다 grid-rows-[1fr]/grid-rows-[0fr] 클래스가 번갈아 적용되고, 콘텐츠는 계속 DOM에 남아있다", async () => {
    const user = userEvent.setup();
    render(<DagNode node={nodeWithDetail} />);

    const wrapper = screen.getByTestId("dag-node-detail-wrapper");
    expect(wrapper.className).toContain("grid-rows-[1fr]");
    expect(wrapper.className).not.toContain("grid-rows-[0fr]");

    const header = screen.getByText("PCTC 해상운송 부산→유럽").closest("div")!;
    await user.click(header);

    expect(wrapper.className).toContain("grid-rows-[0fr]");
    // 조건부 마운트가 아니라 조건부 클래스이므로, 접혀도 콘텐츠는 여전히 DOM에 존재한다
    expect(screen.getByText(/불확실성: medium/)).toBeInTheDocument();

    await user.click(header);
    expect(wrapper.className).toContain("grid-rows-[1fr]");
  });
});

describe("DagNode — detail이 없는 노드는 클릭해도 변화가 없다(회귀 테스트)", () => {
  it("node.detail이 없으면 클릭 핸들러가 붙지 않고 상세 래퍼 자체가 렌더링되지 않는다", async () => {
    const user = userEvent.setup();
    render(<DagNode node={nodeWithoutDetail} />);

    expect(screen.queryByTestId("dag-node-detail-wrapper")).not.toBeInTheDocument();

    const header = screen.getByText("아산 라인").closest("div")!;
    expect(header.className).not.toContain("cursor-pointer");

    await user.click(header);
    // 클릭 후에도 여전히 상세 래퍼가 나타나지 않는다
    expect(screen.queryByTestId("dag-node-detail-wrapper")).not.toBeInTheDocument();
  });
});
