import { describe, expect, it } from "vitest";
import { summarizeDeadline } from "../format";

const NOW = new Date("2026-08-13T00:00:00Z");

describe("summarizeDeadline — 정상 시나리오(happy path)", () => {
  it("2시간 뒤 마감이면 '2시간 후'를 반환하고 overdue는 false다", () => {
    const result = summarizeDeadline("2026-08-13T02:00:00Z", NOW);
    expect(result).toEqual({ label: "2시간 후", overdue: false });
  });

  it("3일 뒤 마감이면 '3일 후'를 반환한다", () => {
    const result = summarizeDeadline("2026-08-16T00:00:00Z", NOW);
    expect(result.label).toBe("3일 후");
    expect(result.overdue).toBe(false);
  });
});

describe("summarizeDeadline — 경계값", () => {
  it("60분 미만이면 분 단위로 표시한다", () => {
    const result = summarizeDeadline("2026-08-13T00:30:00Z", NOW);
    expect(result.label).toBe("30분 후");
  });

  it("정확히 마감 시각이면 기한 초과로 처리한다", () => {
    const result = summarizeDeadline("2026-08-13T00:00:00Z", NOW);
    expect(result.overdue).toBe(true);
  });
});

describe("summarizeDeadline — 예외 케이스", () => {
  it("마감을 이미 지났으면 '결정기한 초과'와 overdue: true를 반환한다", () => {
    const result = summarizeDeadline("2026-08-12T00:00:00Z", NOW);
    expect(result).toEqual({ label: "초과", overdue: true });
  });

  it("deadline이 null이면 '결정기한 미산정'을 반환한다 (DAG에 예상시각 노드가 없는 경우)", () => {
    const result = summarizeDeadline(null, NOW);
    expect(result).toEqual({ label: "미산정", overdue: false });
  });
});
