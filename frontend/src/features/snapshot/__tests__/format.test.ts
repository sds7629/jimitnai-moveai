import { describe, expect, it } from "vitest";
import { summarizeSnapshot } from "../format";
import type { OperationalSnapshotApi } from "../types";

function snapshot(overrides: Partial<OperationalSnapshotApi> = {}): OperationalSnapshotApi {
  return {
    id: 1,
    incident_id: 1,
    data_version: "v1",
    scenario_version: "strike-v1",
    assumptions: ["가정 A"],
    operational_state: {},
    quality_mode: "normal",
    freshness_seconds: 125,
    coverage_ratio: 0.8,
    created_at: "2026-08-13T00:00:00Z",
    ...overrides,
  };
}

describe("summarizeSnapshot — 정상 시나리오(happy path)", () => {
  it("data_version/scenario_version/assumptions를 그대로 옮기고, quality_mode='normal'은 '정상'으로 라벨링한다", () => {
    const summary = summarizeSnapshot(snapshot());
    expect(summary.dataVersion).toBe("v1");
    expect(summary.scenarioVersion).toBe("strike-v1");
    expect(summary.qualityModeLabel).toBe("정상");
    expect(summary.assumptions).toEqual(["가정 A"]);
  });

  it("coverage_ratio 0.8은 '80%'로 변환한다", () => {
    expect(summarizeSnapshot(snapshot({ coverage_ratio: 0.8 })).coverageLabel).toBe("80%");
  });

  it("freshness_seconds 125초는 '2분 전'으로 변환한다", () => {
    expect(summarizeSnapshot(snapshot({ freshness_seconds: 125 })).freshnessLabel).toBe("2분 전");
  });
});

describe("summarizeSnapshot — quality_mode 분기", () => {
  it("'limited'는 '제한 모드'로 라벨링한다", () => {
    expect(summarizeSnapshot(snapshot({ quality_mode: "limited" })).qualityModeLabel).toBe("제한 모드");
  });

  it("알 수 없는 값은 원본 문자열을 그대로 보여준다(방어적 처리)", () => {
    expect(summarizeSnapshot(snapshot({ quality_mode: "unknown_mode" })).qualityModeLabel).toBe("unknown_mode");
  });
});

describe("summarizeSnapshot — freshness 경계값", () => {
  it("60초 미만은 '방금 전'", () => {
    expect(summarizeSnapshot(snapshot({ freshness_seconds: 30 })).freshnessLabel).toBe("방금 전");
  });

  it("3600초 이상은 시간 단위로 표시", () => {
    expect(summarizeSnapshot(snapshot({ freshness_seconds: 7200 })).freshnessLabel).toBe("2시간 전");
  });

  it("86400초 이상은 일 단위로 표시", () => {
    expect(summarizeSnapshot(snapshot({ freshness_seconds: 172800 })).freshnessLabel).toBe("2일 전");
  });
});

describe("summarizeSnapshot — null 값 예외 케이스", () => {
  it("freshness_seconds가 null이면 '-'를 표시한다", () => {
    expect(summarizeSnapshot(snapshot({ freshness_seconds: null })).freshnessLabel).toBe("-");
  });

  it("coverage_ratio가 null이면 '-'를 표시한다", () => {
    expect(summarizeSnapshot(snapshot({ coverage_ratio: null })).coverageLabel).toBe("-");
  });
});
