import type { OperationalSnapshotApi } from "./types";

export interface SnapshotSummary {
  dataVersion: string;
  scenarioVersion: string;
  qualityModeLabel: string;
  freshnessLabel: string;
  coverageLabel: string;
  assumptions: string[];
}

const QUALITY_MODE_LABEL: Record<string, string> = {
  normal: "정상",
  limited: "제한 모드",
};

/** 알려지지 않은 quality_mode 값이 와도 원본 문자열을 그대로 보여줘 방어적으로 처리한다 */
export function formatQualityMode(mode: string): string {
  return QUALITY_MODE_LABEL[mode] ?? mode;
}

/**
 * quality_mode/freshness_seconds/coverage_ratio는 decision-package의 freshness_and_coverage
 * 섹션(Phase 16)에도 그대로 나오므로, 화면 표시 문구를 이 파일에서 export해 재사용한다.
 */
export function formatFreshness(seconds: number | null): string {
  if (seconds === null) return "-";
  if (seconds < 60) return "방금 전";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}분 전`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}시간 전`;
  return `${Math.floor(seconds / 86400)}일 전`;
}

export function formatCoverage(ratio: number | null): string {
  if (ratio === null) return "-";
  return `${Math.round(ratio * 100)}%`;
}

/**
 * OperationalSnapshotApi를 화면 표시용 문자열로 변환한다.
 * simulation-supply-chain-tool.md §3.3 데이터 품질 게이트(freshness/coverage 표시) 요구사항 대응.
 */
export function summarizeSnapshot(snapshot: OperationalSnapshotApi): SnapshotSummary {
  return {
    dataVersion: snapshot.data_version,
    scenarioVersion: snapshot.scenario_version,
    qualityModeLabel: formatQualityMode(snapshot.quality_mode),
    freshnessLabel: formatFreshness(snapshot.freshness_seconds),
    coverageLabel: formatCoverage(snapshot.coverage_ratio),
    assumptions: snapshot.assumptions,
  };
}
