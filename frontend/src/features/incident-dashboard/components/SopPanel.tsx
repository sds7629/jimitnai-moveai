import { useState } from "react";
import type { MatchedSop } from "../types";

function SopItem({ sop }: { sop: MatchedSop }) {
  const expandable = Boolean(sop.steps && sop.steps.length > 0);
  const [open, setOpen] = useState(true);

  return (
    <div className="border-b border-[var(--border)] py-2.5 last:border-b-0">
      <div
        onClick={expandable ? () => setOpen((o) => !o) : undefined}
        className={`flex items-center justify-between ${expandable ? "cursor-pointer" : ""}`}
      >
        <div>
          <div
            className={
              expandable
                ? "text-[12.5px] font-bold text-[var(--text-primary)]"
                : "text-[12.5px] text-[var(--text-secondary-strong)]"
            }
          >
            {sop.code} {sop.title}
          </div>
          <div className="mt-0.5 text-[10px] text-[var(--text-tertiary)]">주관: {sop.owningTeam}</div>
        </div>
        <div className="text-[11px] text-[var(--text-secondary)]">{expandable ? (open ? "▾" : "▸") : "▸"}</div>
      </div>

      {expandable && open && (
        <div className="mt-2 text-[11px] leading-loose text-[var(--text-secondary)]">
          <ol className="list-none">
            {sop.steps!.map((step, index) => (
              <li key={index}>
                {index + 1}. {step}
              </li>
            ))}
          </ol>
          {sop.reference && (
            <div className="mt-2 text-[9.5px] text-[var(--text-tertiary)]">근거: {sop.reference}</div>
          )}
        </div>
      )}
    </div>
  );
}

interface SopPanelProps {
  sops: MatchedSop[];
  matchedCount: number;
  showDemoNote: boolean;
}

/** SOP 자동 매칭 패널. 승인 전 참고용 안내이며, 승인 후 배포용 SOP 화면과는 별개 용도로 추정된다
 * (frontend/DAG_SCREEN_DESIGN_BRIEF.md §6 미확인 사항 참고). */
export function SopPanel({ sops, matchedCount, showDemoNote }: SopPanelProps) {
  return (
    <div className="flex-1 rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
      <div className="mb-1 flex items-baseline gap-2">
        <div className="text-[13.5px] font-bold text-[var(--text-secondary-strong)]">관련 SOP 자동 안내</div>
        <div className="text-[10.5px] text-[var(--text-tertiary)]">{matchedCount}건 매칭</div>
      </div>
      <div className="mb-3 text-[11px] leading-normal text-[var(--text-tertiary)]">
        상황 분석 결과에 맞는 대응 절차를 자동으로 찾아줍니다.
        {showDemoNote && <span className="text-[var(--amber)]"> ※ 데모용 예시 SOP</span>}
      </div>

      {sops.map((sop) => (
        <SopItem key={sop.code} sop={sop} />
      ))}
    </div>
  );
}
