import type { ExcludedCandidate, ResponseCandidate } from "../types";
import { CandidateRow } from "./CandidateRow";

interface CandidateRankingPanelProps {
  candidates: ResponseCandidate[];
  excludedCandidates: ExcludedCandidate[];
}

/**
 * 대응안 후보 랭킹 패널.
 * Phase 5부터 실제 GET /candidates 응답을 기대손실(expected_loss) 오름차순으로 정렬해서 보여준다 —
 * "개별 적용 vs 누적 적용" 구분은 실제 백엔드에 그런 랭킹 개념 자체가 없어서 제거했다
 * (frontend/docs/FEATURE_PHASES.md Phase 5).
 */
export function CandidateRankingPanel({ candidates, excludedCandidates }: CandidateRankingPanelProps) {
  return (
    <div className="flex-[1.2] rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
      <div className="mb-1 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">대응안 후보 랭킹</div>
      <div className="mb-3 text-[10.5px] text-[var(--text-tertiary)]">
        기대손실(expected_loss)이 낮은 순서로 정렬했습니다
      </div>

      {candidates.length === 0 && (
        <div className="rounded-md border border-dashed border-[var(--border-dashed)] px-3 py-3 text-[11px] text-[var(--text-secondary)]">
          아직 시뮬레이션 결과가 없습니다. "다시 실행"을 눌러 계산하세요.
        </div>
      )}

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
