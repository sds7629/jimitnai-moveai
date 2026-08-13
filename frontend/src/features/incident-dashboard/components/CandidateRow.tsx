import { useState } from "react";
import type { ResponseCandidate } from "../types";

interface CandidateRowProps {
  candidate: ResponseCandidate;
}

/** 대응안 후보 랭킹 한 줄. 상세(detail)가 있으면 클릭으로 P90/CVaR·baseline 비교 자리표시자를 펼친다 */
export function CandidateRow({ candidate }: CandidateRowProps) {
  const [open, setOpen] = useState(true);
  const clampedRatio = Math.min(100, Math.max(0, candidate.mitigationRatio));

  return (
    <div className="border-b border-[var(--border)] py-2.5 last:border-b-0">
      <div
        onClick={candidate.detail ? () => setOpen((o) => !o) : undefined}
        className={candidate.detail ? "cursor-pointer" : ""}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-5 w-5 items-center justify-center rounded-full border-[1.5px] border-[var(--blue)] text-[11px] font-bold text-[var(--blue)]">
              {candidate.rank}
            </div>
            <div className="text-[13.5px] font-bold text-[var(--text-primary)]">{candidate.name}</div>
          </div>
          <div className="text-[14px] font-bold text-[var(--teal)]">{candidate.savingsAmount}</div>
        </div>
        {candidate.description && (
          <div className="ml-[29px] mt-1 text-[11.5px] text-[var(--text-secondary)]">{candidate.description}</div>
        )}
        <div className="mt-2 h-[5px] overflow-hidden rounded-full bg-[var(--border)]">
          <div
            data-testid="mitigation-bar"
            className="h-full rounded-full bg-[var(--teal)]"
            style={{ width: `${clampedRatio}%` }}
          />
        </div>
        <div className="mt-1.5 text-[10.5px] text-[var(--text-tertiary)]">
          잔여손실 {candidate.remainingLoss}
          {candidate.detail && <span>ㆍ{open ? "▾" : "▸"} 상세보기</span>}
        </div>
      </div>

      {candidate.detail && open && (
        <div className="mt-2.5 rounded-md border border-dashed border-[var(--border-btn)] bg-[var(--panel-bg-2)] p-3">
          <div
            className="flex h-16 items-center justify-center rounded font-mono text-[10px] text-[var(--text-tertiary)]"
            style={{
              backgroundImage:
                "repeating-linear-gradient(45deg, var(--stripe), var(--stripe) 6px, transparent 6px, transparent 12px)",
            }}
          >
            {candidate.detail.distributionPlaceholder}
          </div>
          <div className="mt-2 text-[10.5px] text-[var(--text-tertiary)]">
            {candidate.detail.baselineComparisonPlaceholder}
          </div>
        </div>
      )}
    </div>
  );
}
