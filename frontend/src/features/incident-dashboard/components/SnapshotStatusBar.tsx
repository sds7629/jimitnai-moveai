import type { SnapshotSummary } from "../../snapshot/format";

interface SnapshotStatusBarProps {
  snapshot: SnapshotSummary;
}

/**
 * 운영 스냅샷 상태 바 — 데이터 버전/시나리오 버전/품질 모드/freshness/coverage를 표시한다.
 * simulation-supply-chain-tool.md §3.3 데이터 품질 게이트 요구사항. 와이어프레임에는 없던
 * 영역이라 frontend/docs/FEATURE_PHASES.md Phase 3에서 새로 추가했다.
 */
export function SnapshotStatusBar({ snapshot }: SnapshotStatusBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 border-b border-[var(--border)] bg-[var(--panel-bg-2)] px-7 py-2 text-[10.5px] text-[var(--text-secondary)]">
      <span>데이터 버전 {snapshot.dataVersion}</span>
      <span>시나리오 {snapshot.scenarioVersion}</span>
      <span>
        품질 모드{" "}
        <span
          className={
            snapshot.qualityModeLabel === "제한 모드" ? "font-semibold text-[var(--amber)]" : "font-semibold"
          }
        >
          {snapshot.qualityModeLabel}
        </span>
      </span>
      <span>최신성 {snapshot.freshnessLabel}</span>
      <span>커버리지 {snapshot.coverageLabel}</span>
      {snapshot.assumptions.length > 0 && <span>가정 {snapshot.assumptions.length}건</span>}
    </div>
  );
}
