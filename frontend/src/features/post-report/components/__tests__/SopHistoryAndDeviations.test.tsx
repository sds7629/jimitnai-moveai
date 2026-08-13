import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SopHistoryAndDeviations } from "../SopHistoryAndDeviations";
import type { DeviationHistorySection, SopHistorySection } from "../../types";

const sopHistory: SopHistorySection = {
  sop_count: 2,
  dispatches: [
    {
      sop_id: 1,
      incident_id: 10,
      role: "항만",
      approval_id: 5,
      action_summary: "선복 재예약 진행",
      dispatched_at: "2026-08-10T09:00:00Z",
      dispatched_by: "김운영",
      status: "완료",
      received_at: "2026-08-10T09:05:00Z",
      accepted_at: "2026-08-10T09:10:00Z",
      completed_at: "2026-08-10T10:00:00Z",
      failed_at: null,
      events: [],
    },
    {
      sop_id: 2,
      incident_id: 10,
      role: "운송",
      approval_id: 5,
      action_summary: "대체 트럭 배차",
      dispatched_at: "2026-08-10T09:00:00Z",
      dispatched_by: "김운영",
      status: "실패",
      received_at: null,
      accepted_at: null,
      completed_at: null,
      failed_at: "2026-08-10T09:30:00Z",
      events: [],
    },
  ],
};

const deviationHistory: DeviationHistorySection = {
  deviation_event_count: 2,
  events: [
    {
      id: 1,
      event_type: "자원_확보_실패",
      actor: "system",
      reason: "대체 선사 선복 없음",
      sop_id: 2,
      status: "실패",
      payload: {},
      created_at: "2026-08-10T09:30:00Z",
      is_deviation_event: true,
    },
    {
      id: 2,
      event_type: "에스컬레이션",
      actor: "김운영",
      reason: "SLA 초과 예상",
      sop_id: null,
      status: null,
      payload: {},
      created_at: "2026-08-10T11:00:00Z",
      is_deviation_event: true,
    },
  ],
};

describe("SopHistoryAndDeviations — SOP 이력 정상 시나리오(happy path)", () => {
  it("dispatches 여러 건을 role·action_summary·status·발송자로 렌더링한다", () => {
    render(<SopHistoryAndDeviations sopHistory={sopHistory} deviationHistory={deviationHistory} />);

    expect(screen.getByText("항만")).toBeInTheDocument();
    expect(screen.getByText("선복 재예약 진행")).toBeInTheDocument();
    expect(screen.getByText("완료")).toBeInTheDocument();
    expect(screen.getByText("운송")).toBeInTheDocument();
    expect(screen.getByText("대체 트럭 배차")).toBeInTheDocument();
    expect(screen.getByText("실패")).toBeInTheDocument();
    expect(screen.getAllByText(/발송자 김운영/).length).toBe(2);
  });

  it("sop_count를 요약 문구로 표시한다", () => {
    render(<SopHistoryAndDeviations sopHistory={sopHistory} deviationHistory={deviationHistory} />);

    expect(screen.getByText(/발송 2건/)).toBeInTheDocument();
  });
});

describe("SopHistoryAndDeviations — SOP 이력 경계값/예외", () => {
  it("dispatches가 빈 배열이면 안내 문구를 표시한다", () => {
    const empty: SopHistorySection = { sop_count: 0, dispatches: [] };

    render(<SopHistoryAndDeviations sopHistory={empty} deviationHistory={deviationHistory} />);

    expect(screen.getByText("SOP가 발송되지 않았습니다.")).toBeInTheDocument();
  });

  it("role이 null인 항목은 '담당자 미상'으로 표시한다", () => {
    const withNullRole: SopHistorySection = {
      sop_count: 1,
      dispatches: [
        {
          sop_id: 3,
          incident_id: 10,
          role: null,
          approval_id: null,
          action_summary: null,
          dispatched_at: "2026-08-10T09:00:00Z",
          dispatched_by: "이운영",
          status: "발송",
          received_at: null,
          accepted_at: null,
          completed_at: null,
          failed_at: null,
          events: [],
        },
      ],
    };

    render(<SopHistoryAndDeviations sopHistory={withNullRole} deviationHistory={deviationHistory} />);

    expect(screen.getByText("담당자 미상")).toBeInTheDocument();
    expect(screen.getByText("발송")).toBeInTheDocument();
  });
});

describe("SopHistoryAndDeviations — 편차 이력 정상 시나리오(happy path)", () => {
  it("deviation_event_count > 0이면 요약 문구와 TimelineView 이벤트를 함께 렌더링한다", () => {
    render(<SopHistoryAndDeviations sopHistory={sopHistory} deviationHistory={deviationHistory} />);

    expect(screen.getByText(/편차\/에스컬레이션 2건/)).toBeInTheDocument();
    expect(screen.getByText(/자원_확보_실패/)).toBeInTheDocument();
    expect(screen.getAllByText(/에스컬레이션/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/SLA 초과 예상/)).toBeInTheDocument();
  });
});

describe("SopHistoryAndDeviations — 편차 이력 경계값", () => {
  it("events가 빈 배열이면 TimelineView의 빈 상태 문구를 그대로 노출한다", () => {
    const emptyDeviation: DeviationHistorySection = { deviation_event_count: 0, events: [] };

    render(<SopHistoryAndDeviations sopHistory={sopHistory} deviationHistory={emptyDeviation} />);

    expect(screen.getByText("타임라인이 아직 없습니다.")).toBeInTheDocument();
  });

  it("deviation_event_count가 0이어도 요약 문구 자체는 표시한다", () => {
    const emptyDeviation: DeviationHistorySection = { deviation_event_count: 0, events: [] };

    render(<SopHistoryAndDeviations sopHistory={sopHistory} deviationHistory={emptyDeviation} />);

    expect(screen.getByText(/편차\/에스컬레이션 0건/)).toBeInTheDocument();
  });
});
