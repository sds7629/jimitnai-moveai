import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
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
    expect(screen.getByText("완료")).toBeInTheDocument();
    expect(screen.getByText("우선 반출 대상 컨테이너 처리")).toBeInTheDocument();
  });
});

describe("SopDispatchPanel — 경계값(빈 상태)", () => {
  it("발송된 SOP가 없으면 안내 문구를 표시한다", () => {
    render(<SopDispatchPanel sopStatuses={[]} />);
    expect(screen.getByText(/아직 SOP가 발송되지 않았습니다/)).toBeInTheDocument();
  });
});
