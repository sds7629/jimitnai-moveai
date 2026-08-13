import type {
  CandidateSummaryApi,
  DynamicVariableChangesSection,
  ExpectedVsActualProgressSection,
  SnapshotChangeApi,
  SnapshotVersionApi,
} from "../types";
import { formatKrwToEokwon } from "../../../lib/currency";
import { formatCoverage, formatFreshness, formatQualityMode } from "../../snapshot/format";

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

/** 백엔드 confidence는 0~1 실수라 화면에서는 %로 바꿔 보여준다 (features/candidates/mapping.ts와 동일 규칙) */
function formatConfidence(confidence: number | null | undefined): string | null {
  if (confidence == null) return null;
  return `${Math.round(confidence * 100)}%`;
}

/** changes_summary 유니온 판별 — 0~1개 이력이면 안내 문구 string[], 2개 이상이면 diff 객체 배열 */
function isChangeDetailList(summary: string[] | SnapshotChangeApi[]): summary is SnapshotChangeApi[] {
  return summary.length > 0 && typeof summary[0] !== "string";
}

function CandidateCard({ label, candidate }: { label: string; candidate: CandidateSummaryApi }) {
  return (
    <div className="flex-1 rounded-md border border-[var(--border)] bg-[var(--panel-bg-2)] p-3">
      <div className="mb-2 text-[10.5px] font-bold text-[var(--text-tertiary)]">{label}</div>
      {!candidate.available ? (
        <div className="text-[11px] text-[var(--text-secondary)]">해당 후보 없음</div>
      ) : (
        <>
          <div className="text-[12.5px] font-bold text-[var(--text-primary)]">{candidate.candidate_type}</div>
          {candidate.description && (
            <div className="mt-0.5 text-[10.5px] text-[var(--text-secondary)]">{candidate.description}</div>
          )}
          {candidate.simulation.available ? (
            <>
              <div className="mt-2 text-[10.5px] text-[var(--text-tertiary)]">기대손실</div>
              <div className="text-[13px] font-bold">{formatKrwToEokwon(candidate.simulation.expected_loss ?? null)}</div>
              <div className="mt-1 text-[10.5px] text-[var(--text-tertiary)]">
                P90 {formatKrwToEokwon(candidate.simulation.p90 ?? null)} · CVaR{" "}
                {formatKrwToEokwon(candidate.simulation.cvar ?? null)}
              </div>
              {formatConfidence(candidate.simulation.confidence) !== null && (
                <div className="mt-1 text-[10.5px] text-[var(--text-tertiary)]">
                  신뢰도 {formatConfidence(candidate.simulation.confidence)}
                </div>
              )}
            </>
          ) : (
            <div className="mt-2 text-[10.5px] text-[var(--text-secondary)]">
              {candidate.simulation.reason ?? "시뮬레이션 결과 없음"}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SnapshotVersionRow({ version }: { version: SnapshotVersionApi }) {
  return (
    <div className="rounded-md border border-[var(--border)] bg-[var(--panel-bg-2)] p-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10.5px] font-bold text-[var(--text-secondary-strong)]">버전 {version.snapshot_id}</span>
        <span className="rounded-full border border-[var(--border-mid)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
          {formatQualityMode(version.quality_mode)}
        </span>
        <span className="rounded-full border border-[var(--border-mid)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
          최신성 {formatFreshness(version.freshness_seconds)}
        </span>
        <span className="rounded-full border border-[var(--border-mid)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
          커버리지 {formatCoverage(version.coverage_ratio)}
        </span>
      </div>
      <div className="mt-1 text-[10.5px] text-[var(--text-tertiary)]">
        데이터 {version.data_version} · 시나리오 {version.scenario_version} · {formatDateTime(version.created_at)}
      </div>
      {version.assumptions.length > 0 && (
        <ul className="mt-1 list-disc pl-4 text-[10.5px] text-[var(--text-secondary)]">
          {version.assumptions.map((assumption) => (
            <li key={assumption}>{assumption}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

interface ExpectedProgressAndChangesProps {
  progress: ExpectedVsActualProgressSection;
  changes: DynamicVariableChangesSection;
}

/**
 * 사후보고서 Phase 20 — sections["2_최초_예상과_실제_진행_과정"] +
 * sections["3_주요_동적_변수의_변화"]를 타임라인형 비교 카드 하나로 렌더링한다
 * (frontend/docs/FEATURE_PHASES.md Phase 20).
 *
 * 섹션 2는 baseline(무대응) vs 승인 후보 2장 비교이고, 실제 진행값은 스코프 제약상
 * 항상 미확정이라 그 사유를 그대로 노출한다. 섹션 3의 freshness/coverage 문구는
 * features/snapshot/format.ts의 포맷 함수를 재사용해 다른 화면과 표현을 통일한다.
 */
export function ExpectedProgressAndChanges({ progress, changes }: ExpectedProgressAndChangesProps) {
  const { changes_summary: changesSummary } = changes;

  return (
    <div className="rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
      <div className="mb-3 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">
        최초 예상 · 실제 진행 · 동적 변수 변화
      </div>

      <div className="flex gap-3">
        <CandidateCard label="최초 예상(무대응 baseline)" candidate={progress.expected.baseline} />
        <CandidateCard label="승인 후보" candidate={progress.expected.approved_candidate} />
      </div>

      <div className="mt-2 rounded-md border border-dashed border-[var(--border-dashed)] px-3 py-2 text-[10.5px] text-[var(--text-secondary)]">
        실제 진행: {progress.actual_status} — {progress.actual_progress.reason}
      </div>

      <div className="mt-3 border-t border-[var(--border)] pt-2.5">
        <div className="mb-1.5 text-[10.5px] font-bold text-[var(--text-secondary-strong)]">
          스냅샷 버전 타임라인 ({changes.snapshot_count}건)
        </div>
        {changes.versions.length === 0 ? (
          <div className="text-[10.5px] text-[var(--text-secondary)]">스냅샷 이력이 없습니다.</div>
        ) : (
          <div className="flex flex-col gap-2">
            {changes.versions.map((version) => (
              <SnapshotVersionRow key={version.snapshot_id} version={version} />
            ))}
          </div>
        )}

        <div className="mt-2.5">
          <div className="mb-1 text-[10.5px] font-bold text-[var(--text-secondary-strong)]">버전 간 변화</div>
          {isChangeDetailList(changesSummary) ? (
            <ul className="list-disc pl-4 text-[10.5px] text-[var(--text-secondary)]">
              {changesSummary.map((change) => (
                <li key={`${change.from_snapshot_id}-${change.to_snapshot_id}`}>
                  버전 {change.from_snapshot_id} → 버전 {change.to_snapshot_id}: {change.summary}
                </li>
              ))}
            </ul>
          ) : (
            <ul className="list-disc pl-4 text-[10.5px] text-[var(--text-secondary)]">
              {(changesSummary as string[]).map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
