import type { FinalDecisionSection, OverviewSection } from "../types";

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

interface OverviewAndDecisionCardProps {
  overview: OverviewSection;
  decision: FinalDecisionSection;
}

/**
 * 사후보고서 Phase 19 — sections["1_사건_개요와_발생시점"] + sections["5_최종_결정과_승인자"]를
 * 요약 카드 하나로 렌더링한다 (frontend/docs/FEATURE_PHASES.md Phase 19).
 */
export function OverviewAndDecisionCard({ overview, decision }: OverviewAndDecisionCardProps) {
  const affectedEntries = Object.entries(overview.affected_targets);

  return (
    <div className="rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
      <div className="mb-3 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">사건 개요 · 최종 결정</div>

      <div className="flex flex-wrap gap-1.5">
        <span className="rounded-full border border-[var(--border-mid)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
          {overview.type}
        </span>
        <span className="rounded-full border border-[var(--border-mid)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
          {overview.location}
        </span>
        <span className="rounded-full border border-[var(--border-mid)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
          {overview.status}
        </span>
      </div>
      <div className="mt-1.5 text-[10.5px] text-[var(--text-tertiary)]">발생 {formatDateTime(overview.occurred_at)}</div>

      {affectedEntries.length > 0 && (
        <div className="mt-2 text-[10.5px] text-[var(--text-secondary)]">
          {affectedEntries.map(([key, value]) => (
            <div key={key}>
              ㆍ{key}: {Array.isArray(value) ? value.join(", ") : String(value)}
            </div>
          ))}
        </div>
      )}

      <div className="mt-2">
        <div className="mb-1 text-[10.5px] font-bold text-[var(--text-secondary-strong)]">접수 시점 가정</div>
        {overview.assumptions_at_intake.length === 0 ? (
          <div className="text-[10.5px] text-[var(--text-secondary)]">등록된 가정이 없습니다.</div>
        ) : (
          <ul className="list-disc pl-4 text-[10.5px] text-[var(--text-secondary)]">
            {overview.assumptions_at_intake.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-3 border-t border-[var(--border)] pt-2.5">
        <div className="mb-1 text-[10.5px] font-bold text-[var(--text-secondary-strong)]">최종 결정</div>
        {decision.final_decision.available ? (
          <div className="rounded-md border border-[var(--border)] bg-[var(--panel-bg-2)] p-2.5 text-[10.5px] text-[var(--text-secondary)]">
            <span className="font-bold text-[var(--text-primary)]">{decision.final_decision.decision_type}</span>
            {" ㆍ "}
            {decision.final_decision.approver}
            {" ㆍ "}
            {formatDateTime(decision.final_decision.decided_at)}
            <div className="mt-1">사유: {decision.final_decision.reason}</div>
          </div>
        ) : (
          <div className="text-[10.5px] text-[var(--text-secondary)]">{decision.final_decision.reason}</div>
        )}

        {decision.approvals_history.length > 0 && (
          <div className="mt-2 text-[10.5px] text-[var(--text-tertiary)]">
            승인 이력 {decision.approvals_history.length}건
          </div>
        )}
      </div>
    </div>
  );
}
