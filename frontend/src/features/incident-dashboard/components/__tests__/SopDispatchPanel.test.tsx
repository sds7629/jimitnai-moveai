import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SopDispatchPanel } from "../SopDispatchPanel";
import type { SopStatusItemApi } from "../../../sop-dispatch/types";

function sopItem(overrides: Partial<SopStatusItemApi> = {}): SopStatusItemApi {
  return {
    sop_id: 1,
    incident_id: 2,
    role: "항만",
    approval_id: 5,
    action_summary: "우선 반출 대상 컨테이너 처리",
    dispatched_at: "2026-08-13T03:00:00Z",
    dispatched_by: "김담당",
    status: "발송",
    received_at: null,
    accepted_at: null,
    completed_at: null,
    failed_at: null,
    events: [],
    ...overrides,
  };
}

describe("SopDispatchPanel — 정상 시나리오(happy path)", () => {
  it("역할별 SOP 발송 상태를 렌더링한다", () => {
    render(
      <SopDispatchPanel
        sopStatuses={[
          sopItem({ role: "항만", status: "발송" }),
          sopItem({ sop_id: 2, role: "운송", status: "완료", action_summary: "긴급 차량 배차" }),
        ]}
      />,
    );

    expect(screen.getByText("항만")).toBeInTheDocument();
    expect(screen.getByText("운송")).toBeInTheDocument();
    expect(screen.getByText("발송")).toBeInTheDocument();
    // "완료"는 상태 배지 텍스트와 상태 전이 버튼 라벨에 둘 다 쓰여 여러 개 나온다
    expect(screen.getAllByText("완료").length).toBeGreaterThan(0);
    expect(screen.getByText("우선 반출 대상 컨테이너 처리")).toBeInTheDocument();
  });
});

describe("SopDispatchPanel — 경계값(빈 상태)", () => {
  it("발송된 SOP가 없으면 안내 문구를 표시한다", () => {
    render(<SopDispatchPanel sopStatuses={[]} />);
    expect(screen.getByText(/아직 SOP가 발송되지 않았습니다/)).toBeInTheDocument();
  });
});

describe("SopDispatchPanel — 상태 전이", () => {
  it("실행자를 입력하고 상태 버튼을 누르면 onStatusUpdate가 호출된다", async () => {
    const user = userEvent.setup();
    const onStatusUpdate = vi.fn();
    render(<SopDispatchPanel sopStatuses={[sopItem({ sop_id: 7, role: "항만" })]} onStatusUpdate={onStatusUpdate} />);

    await user.type(screen.getByLabelText("실행자"), "박현장");
    await user.click(screen.getByRole("button", { name: "수신" }));

    expect(onStatusUpdate).toHaveBeenCalledWith(7, "수신", "박현장");
  });

  it("실행자를 입력하지 않으면 onStatusUpdate를 호출하지 않는다", async () => {
    const user = userEvent.setup();
    const onStatusUpdate = vi.fn();
    render(<SopDispatchPanel sopStatuses={[sopItem({ sop_id: 7 })]} onStatusUpdate={onStatusUpdate} />);

    await user.click(screen.getByRole("button", { name: "수신" }));

    expect(onStatusUpdate).not.toHaveBeenCalled();
    expect(screen.getByText(/실행자를 입력/)).toBeInTheDocument();
  });

  it("isUpdating이 true면 상태 버튼이 비활성화된다", () => {
    render(<SopDispatchPanel sopStatuses={[sopItem({ sop_id: 7 })]} isUpdating />);
    expect(screen.getByRole("button", { name: "수신" })).toBeDisabled();
  });

  it("updateError가 있으면 에러 메시지를 표시한다", () => {
    render(<SopDispatchPanel sopStatuses={[sopItem({ sop_id: 7 })]} updateError="서버 오류" />);
    expect(screen.getByText(/서버 오류/)).toBeInTheDocument();
  });
});
