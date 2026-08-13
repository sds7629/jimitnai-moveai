import type { NowVs6hVsNoActionSection, PairSummaryApi } from "../../decision-package/types";
import { formatKrwToEokwon } from "../../../lib/currency";

const SLOTS: { key: keyof NowVs6hVsNoActionSection; label: string }[] = [
  { key: "no_action", label: "무대응" },
  { key: "now", label: "지금 대응" },
  { key: "plus_6h", label: "6시간 후 대응" },
];

function Card({ label, pair }: { label: string; pair: PairSummaryApi | null | undefined }) {
  return (
    <div className="flex-1 rounded-md border border-[var(--border)] bg-[var(--panel-bg-2)] p-3">
      <div className="mb-2 text-[10.5px] font-bold text-[var(--text-tertiary)]">{label}</div>
      {pair == null ? (
        <div className="text-[11px] text-[var(--text-secondary)]">해당 후보 없음</div>
      ) : (
        <>
          <div className="text-[12.5px] font-bold text-[var(--text-primary)]">{pair.candidate_type}</div>
          {pair.description && (
            <div className="mt-0.5 text-[10.5px] text-[var(--text-secondary)]">{pair.description}</div>
          )}
          <div className="mt-2 text-[10.5px] text-[var(--text-tertiary)]">기대손실</div>
          <div className="text-[13px] font-bold">{formatKrwToEokwon(pair.expected_loss)}</div>
          <div className="mt-1 text-[10.5px] text-[var(--text-tertiary)]">
            P90 {formatKrwToEokwon(pair.p90)} · CVaR {formatKrwToEokwon(pair.cvar)}
          </div>
        </>
      )}
    </div>
  );
}

interface NowVs6hComparisonProps {
  section: NowVs6hVsNoActionSection;
}

/**
 * 의사결정 근거 Phase 14 — now_vs_6h_vs_no_action을 무대응/지금/6시간후 3장 비교 카드로.
 * frontend/docs/FEATURE_PHASES.md Phase 14.
 */
export function NowVs6hComparison({ section }: NowVs6hComparisonProps) {
  return (
    <div className="flex gap-3">
      {SLOTS.map(({ key, label }) => (
        <Card key={key} label={label} pair={section[key]} />
      ))}
    </div>
  );
}
