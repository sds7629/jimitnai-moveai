import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TimelineView } from "../TimelineView";
import type { TimelineEventApi } from "../../../execution-tracking/types";

function event(overrides: Partial<TimelineEventApi> = {}): TimelineEventApi {
  return {
    id: 1,
    event_type: "sop_dispatched",
    actor: "시스템",
    reason: null,
    sop_id: 1,
    status: null,
    payload: {},
    created_at: "2026-08-13T03:00:00Z",
    is_deviation_event: false,
    ...overrides,
  };
}

describe("TimelineView — 정상 시나리오(happy path)", () => {
  it("이벤트 목록을 시간순으로 렌더링한다", () => {
    render(
      <TimelineView
        events={[
          event({ id: 1, event_type: "incident_approved", actor: "김담당" }),
          event({ id: 2, event_type: "sop_dispatched", actor: "시스템" }),
        ]}
      />,
    );

    expect(screen.getByText("incident_approved")).toBeInTheDocument();
    expect(screen.getByText("sop_dispatched")).toBeInTheDocument();
    expect(screen.getByText("김담당")).toBeInTheDocument();
  });
});

describe("TimelineView — 편차 이벤트 강조", () => {
  it("is_deviation_event가 true인 항목은 경고 표시를 한다", () => {
    render(<TimelineView events={[event({ id: 1, event_type: "execution_deviation", is_deviation_event: true })]} />);
    expect(screen.getByText(/편차/)).toBeInTheDocument();
  });

  it("is_deviation_event가 false인 항목은 경고 표시가 없다", () => {
    render(<TimelineView events={[event({ id: 1, is_deviation_event: false })]} />);
    expect(screen.queryByText(/편차/)).not.toBeInTheDocument();
  });
});

describe("TimelineView — 경계값(빈 타임라인)", () => {
  it("이벤트가 없으면 안내 문구를 표시한다", () => {
    render(<TimelineView events={[]} />);
    expect(screen.getByText(/타임라인이 아직 없습니다/)).toBeInTheDocument();
  });
});
