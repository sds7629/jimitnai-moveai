import type { RankedCandidatesSection } from "../../decision-package/types";
import { formatKrwToEokwon } from "../../../lib/currency";

interface RankedCandidatesListProps {
  section: RankedCandidatesSection;
}

/**
 * 의사결정 근거 Phase 18 — ranked_candidates(서버가 계산한 composite score 순위)를
 * 순위 리스트로 렌더링한다. composite_score는 대응안 후보 랭킹 패널(features/candidates,
 * 절감액 기준 정렬)과는 다른 알고리즘(기대손실/P90/CVaR 가중합 × 실행가능성 페널티)이라
 * 별도 표시임을 라벨에서 구분한다 (frontend/docs/FEATURE_PHASES.md Phase 18).
 */
export function RankedCandidatesList({ section }: RankedCandidatesListProps) {
  const { ranked, excluded_from_ranking: excluded } = section;

  if (ranked.length === 0 && excluded.length === 0) {
    return <div className="text-[11px] text-[var(--text-secondary)]">순위화된 후보가 없습니다.</div>;
  }

  return (
    <div className="flex flex-col gap-2">
      {ranked.map((candidate) => (
        <div
          key={candidate.candidate_id}
          className="flex gap-3 rounded-md border border-[var(--border)] bg-[var(--panel-bg-2)] p-3"
        >
          <div className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full border-[1.5px] border-[var(--blue)] text-[11px] font-bold text-[var(--blue)]">
            {candidate.rank}
          </div>
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <div className="text-[12.5px] font-bold text-[var(--text-primary)]">{candidate.candidate_type}</div>
              <div className="text-[10.5px] text-[var(--text-tertiary)]">
                composite score {candidate.composite_score.toLocaleString("ko-KR")}
              </div>
            </div>
            {candidate.description && (
              <div className="mt-0.5 text-[10.5px] text-[var(--text-secondary)]">{candidate.description}</div>
            )}
            <div className="mt-1 text-[10.5px] text-[var(--text-tertiary)]">
              기대손실 {formatKrwToEokwon(candidate.expected_loss)} ㆍ P90 {formatKrwToEokwon(candidate.p90)} ㆍ CVaR{" "}
              {formatKrwToEokwon(candidate.cvar)}
            </div>
            {candidate.preconditions.length > 0 && (
              <div className="mt-1 text-[10.5px] text-[var(--text-tertiary)]">
                선행 조건: {candidate.preconditions.join(", ")}
              </div>
            )}
          </div>
        </div>
      ))}

      {excluded.length > 0 && (
        <div className="mt-1">
          <div className="mb-1 text-[10.5px] font-bold text-[var(--text-tertiary)]">순위에서 제외된 후보</div>
          <div className="flex flex-col gap-1.5">
            {excluded.map((candidate) => (
              <div
                key={candidate.candidate_id}
                className="rounded-md border border-dashed border-[var(--border-dashed)] p-2.5 text-[10.5px] text-[var(--text-secondary)]"
              >
                <span className="font-bold text-[var(--text-primary)]">{candidate.candidate_type}</span>
                {" ㆍ "}
                {candidate.reason}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
