import type { ExcludedCandidate, RankingMode, ResponseCandidate } from "../types";
import { CandidateRow } from "./CandidateRow";

const RANKING_CAPTION: Record<RankingMode, string> = {
  individual: "각 후보를 단독으로 적용했을 때의 개별 결과입니다",
  cumulative: "순위는 1→4번 순차 누적 적용 시의 결과입니다",
};

interface CandidateRankingPanelProps {
  candidates: ResponseCandidate[];
  excludedCandidates: ExcludedCandidate[];
  rankingMode: RankingMode;
}

/**
 * 대응안 후보 랭킹 패널.
 * rankingMode에 따라 안내 문구가 바뀐다 — "개별 적용 vs 누적 적용" 계산 의미가
 * frontend/DAG_SCREEN_DESIGN_BRIEF.md §4에서 미정이었던 부분을 prop으로 명시적으로 드러낸 것.
 */
export function CandidateRankingPanel({
  candidates,
  excludedCandidates,
  rankingMode,
}: CandidateRankingPanelProps) {
  return (
    <div className="flex-[1.2] rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
      <div className="mb-1 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">대응안 후보 랭킹</div>
      <div className="mb-3 text-[10.5px] text-[var(--text-tertiary)]">{RANKING_CAPTION[rankingMode]}</div>

      {candidates.map((candidate) => (
        <CandidateRow key={candidate.rank} candidate={candidate} />
      ))}

      {excludedCandidates.length > 0 && (
        <div className="mt-2 border-t border-[var(--border)] pt-3">
          <div className="mb-1.5 text-[11.5px] font-bold text-[var(--text-secondary)]">제외된 대응안</div>
          {excludedCandidates.map((excluded) => (
            <div
              key={excluded.name}
              className="rounded-md border border-dashed border-[var(--border-dashed)] px-2.5 py-2 text-[11px] text-[var(--text-secondary)]"
            >
              <span className="font-semibold text-[var(--text-secondary-strong)]">{excluded.name}</span> —{" "}
              <span className="text-[var(--red)]">{excluded.reason}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
