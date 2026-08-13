import { useState } from "react";
import type { ResponseCandidate } from "../types";

interface CandidateRowProps {
  candidate: ResponseCandidate;
}

function EvidenceSection({ label, colorClass, entries }: { label: string; colorClass: string; entries: [string, unknown][] }) {
  if (entries.length === 0) return null;
  return (
    <div className="mb-1.5">
      <span className={`rounded px-1.5 py-0.5 text-[9.5px] font-bold ${colorClass}`}>{label}</span>
      <div className="mt-1 pl-1">
        {entries.map(([key, value]) => (
          <div key={key}>
            ㆍ{key}: {String(value)}
          </div>
        ))}
      </div>
    </div>
  );
}

/** 대응안 후보 랭킹 한 줄. 상세(detail)가 있으면 클릭으로 P90/CVaR·FACT/INFERENCE/ASSUMPTION을 펼친다 */
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
        <div className="mt-2.5 rounded-md border border-dashed border-[var(--border-btn)] bg-[var(--panel-bg-2)] p-3 text-[10.5px] leading-relaxed text-[var(--text-secondary)]">
          <div className="mb-2">
            {candidate.detail.p90 && <>P90 {candidate.detail.p90} ㆍ </>}
            {candidate.detail.cvar && <>CVaR {candidate.detail.cvar} ㆍ </>}
            {candidate.detail.confidencePercent !== null && <>신뢰도 {candidate.detail.confidencePercent}%</>}
          </div>
          {candidate.detail.sensitivityVariables.length > 0 && (
            <div className="mb-2">
              민감도 변수: {candidate.detail.sensitivityVariables.map((v) => String(v)).join(", ")}
            </div>
          )}
          <EvidenceSection
            label="FACT"
            colorClass="bg-[var(--blue-chip-bg)] text-[var(--blue)]"
            entries={Object.entries(candidate.detail.fact)}
          />
          <EvidenceSection
            label="INFERENCE"
            colorClass="bg-[var(--red-chip-bg)] text-[var(--red)]"
            entries={Object.entries(candidate.detail.inference)}
          />
          <EvidenceSection
            label="ASSUMPTION"
            colorClass="bg-[var(--blue-chip-bg)] text-[var(--amber)]"
            entries={Object.entries(candidate.detail.assumption)}
          />
        </div>
      )}
    </div>
  );
}
