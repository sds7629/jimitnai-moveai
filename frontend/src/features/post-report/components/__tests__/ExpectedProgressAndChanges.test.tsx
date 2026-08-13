import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ExpectedProgressAndChanges } from "../ExpectedProgressAndChanges";
import type { DynamicVariableChangesSection, ExpectedVsActualProgressSection } from "../../types";

const SCOPE_NOTE = "이 시스템에는 실적 확정값(실측 손실, 실제 완료 시각 등)을 입력받는 API가 없습니다";

const progress: ExpectedVsActualProgressSection = {
  expected: {
    baseline: {
      available: true,
      candidate_id: 1,
      candidate_type: "무대응",
      description: "아무 조치도 하지 않음",
      start_time_variant: null,
      simulation: {
        available: true,
        expected_loss: 1_200_000_000,
        p90: 1_800_000_000,
        cvar: 2_100_000_000,
        confidence: 0.82,
        data_version: "d1",
        scenario_version: "s1",
        calculated_at: "2026-08-10T01:00:00Z",
      },
    },
    approved_candidate: {
      available: true,
      candidate_id: 4,
      candidate_type: "대체 항만",
      description: "광양항으로 우회",
      start_time_variant: "now",
      simulation: {
        available: true,
        expected_loss: 400_000_000,
        p90: 700_000_000,
        cvar: 900_000_000,
        confidence: 0.71,
        data_version: "d2",
        scenario_version: "s2",
        calculated_at: "2026-08-11T01:00:00Z",
      },
    },
  },
  actual_status: "미확정",
  actual_progress: { available: false, reason: SCOPE_NOTE },
};

const changes: DynamicVariableChangesSection = {
  snapshot_count: 2,
  versions: [
    {
      snapshot_id: 10,
      data_version: "d1",
      scenario_version: "s1",
      quality_mode: "normal",
      freshness_seconds: 120,
      coverage_ratio: 0.93,
      assumptions: ["항만 재개방 시점 미확정"],
      created_at: "2026-08-10T01:00:00Z",
    },
    {
      snapshot_id: 11,
      data_version: "d2",
      scenario_version: "s2",
      quality_mode: "limited",
      freshness_seconds: 7200,
      coverage_ratio: 0.4,
      assumptions: ["항만 재개방 시점 미확정", "선복 확보 지연"],
      created_at: "2026-08-11T01:00:00Z",
    },
  ],
  changes_summary: [
    {
      from_snapshot_id: 10,
      to_snapshot_id: 11,
      from_created_at: "2026-08-10T01:00:00Z",
      to_created_at: "2026-08-11T01:00:00Z",
      summary: "quality_mode: 'normal' -> 'limited' / 가정 추가: ['선복 확보 지연']",
    },
  ],
};

describe("ExpectedProgressAndChanges — 정상 시나리오(happy path)", () => {
  it("baseline·승인 후보 비교 카드와 스냅샷 버전 타임라인을 함께 표시한다", () => {
    render(<ExpectedProgressAndChanges progress={progress} changes={changes} />);

    expect(screen.getByText("무대응")).toBeInTheDocument();
    expect(screen.getByText("대체 항만")).toBeInTheDocument();
    expect(screen.getByText("광양항으로 우회")).toBeInTheDocument();
    // 기대손실은 억원 단위로 포맷된다 (lib/currency.ts formatKrwToEokwon 재사용)
    expect(screen.getByText("12.0억원")).toBeInTheDocument();
    expect(screen.getByText("4.0억원")).toBeInTheDocument();
    expect(screen.getByText(/신뢰도 82%/)).toBeInTheDocument();
    // 스냅샷 버전 타임라인 — 품질 모드/최신성/커버리지 뱃지
    expect(screen.getByText("정상")).toBeInTheDocument();
    expect(screen.getByText("제한 모드")).toBeInTheDocument();
    expect(screen.getByText("최신성 2분 전")).toBeInTheDocument();
    expect(screen.getByText("커버리지 93%")).toBeInTheDocument();
    // 변화 요약은 "버전 N → 버전 M" 형태로 노출한다
    expect(screen.getByText(/버전 10 → 버전 11/)).toBeInTheDocument();
    expect(screen.getByText(/가정 추가/)).toBeInTheDocument();
  });

  it("실적이 미확정이라는 스코프 제약을 숨기지 않고 그대로 노출한다", () => {
    render(<ExpectedProgressAndChanges progress={progress} changes={changes} />);

    // "미확정"은 스냅샷 가정 목록에도 등장하므로 실제 진행 문구 전체를 정규식으로 특정한다
    expect(screen.getByText(/실제 진행: 미확정/)).toBeInTheDocument();
    expect(screen.getByText(/실적 확정값.*입력받는 API가 없습니다/)).toBeInTheDocument();
  });
});

describe("ExpectedProgressAndChanges — 경계값(스냅샷 1개 이하 · 시뮬레이션 없음)", () => {
  it("changes_summary가 문자열 배열이면 안내 문구로 그대로 표시한다", () => {
    const singleSnapshot: DynamicVariableChangesSection = {
      snapshot_count: 1,
      versions: [changes.versions[0]],
      changes_summary: ["스냅샷이 1개뿐이라 버전 간 변화 이력이 없음 (최초 스냅샷만 존재)"],
    };

    render(<ExpectedProgressAndChanges progress={progress} changes={singleSnapshot} />);

    expect(screen.getByText(/스냅샷이 1개뿐이라/)).toBeInTheDocument();
    expect(screen.queryByText(/버전 10 → 버전 11/)).not.toBeInTheDocument();
  });

  it("후보는 있지만 시뮬레이션이 없으면 시뮬레이션 부재 사유를 표시한다", () => {
    const noSim: ExpectedVsActualProgressSection = {
      ...progress,
      expected: {
        ...progress.expected,
        approved_candidate: {
          available: true,
          candidate_id: 4,
          candidate_type: "대체 항만",
          description: "광양항으로 우회",
          start_time_variant: null,
          simulation: { available: false, reason: "이 후보의 시뮬레이션 결과가 없음" },
        },
      },
    };

    render(<ExpectedProgressAndChanges progress={noSim} changes={changes} />);

    expect(screen.getByText("이 후보의 시뮬레이션 결과가 없음")).toBeInTheDocument();
  });

  it("freshness_seconds와 coverage_ratio가 null이면 '-'로 표시한다", () => {
    const nullMetrics: DynamicVariableChangesSection = {
      snapshot_count: 1,
      versions: [{ ...changes.versions[0], freshness_seconds: null, coverage_ratio: null }],
      changes_summary: ["operational_snapshots 이력이 없음"],
    };

    render(<ExpectedProgressAndChanges progress={progress} changes={nullMetrics} />);

    expect(screen.getByText("최신성 -")).toBeInTheDocument();
    expect(screen.getByText("커버리지 -")).toBeInTheDocument();
  });
});

describe("ExpectedProgressAndChanges — 실패 시나리오(후보·스냅샷 자체가 없음)", () => {
  it("baseline·승인 후보가 모두 없으면 후보 없음 문구를 표시한다", () => {
    const noCandidates: ExpectedVsActualProgressSection = {
      expected: { baseline: { available: false }, approved_candidate: { available: false } },
      actual_status: "미확정",
      actual_progress: { available: false, reason: SCOPE_NOTE },
    };

    render(<ExpectedProgressAndChanges progress={noCandidates} changes={changes} />);

    expect(screen.getAllByText("해당 후보 없음")).toHaveLength(2);
  });

  it("스냅샷 이력이 하나도 없으면 타임라인 대신 안내 문구를 표시한다", () => {
    const empty: DynamicVariableChangesSection = {
      snapshot_count: 0,
      versions: [],
      changes_summary: ["operational_snapshots 이력이 없음"],
    };

    render(<ExpectedProgressAndChanges progress={progress} changes={empty} />);

    expect(screen.getByText("스냅샷 이력이 없습니다.")).toBeInTheDocument();
    expect(screen.getByText(/operational_snapshots 이력이 없음/)).toBeInTheDocument();
  });
});
