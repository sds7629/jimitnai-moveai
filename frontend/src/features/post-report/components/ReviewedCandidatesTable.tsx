import type { ValidationStatus } from "../../candidates/types";
import type { CandidatesReviewedSection, ReviewedCandidateApi } from "../types";

/** incident-dashboard의 FeasibilityTable과 같은 상태별 색 구분 — 두 화면의 톤을 맞춘다 */
const STATUS_COLOR: Record<ValidationStatus, string> = {
  가능: "border-[var(--teal)] text-[var(--teal)]",
  조건부: "border-[var(--amber)] text-[var(--amber)]",
  불가능: "border-[var(--red)] text-[var(--red)]",
  미검증: "border-[var(--border-mid)] text-[var(--text-secondary)]",
};

/** 제외 사유는 카테고리만 있고 detail이 null인 경우가 있어 카테고리 단독 표기도 지원한다 */
function formatExclusion(candidate: ReviewedCandidateApi): string {
  if (!candidate.exclusion_category) return "-";
  if (!candidate.exclusion_detail) return candidate.exclusion_category;
  return `${candidate.exclusion_category} ㆍ ${candidate.exclusion_detail}`;
}

interface ReviewedCandidatesTableProps {
  section: CandidatesReviewedSection;
}

/**
 * 사후보고서 Phase 21 — sections["4_검토한_대응안과_제외_사유"]를
 * 후보별 검토 결과 표로 렌더링한다 (frontend/docs/FEATURE_PHASES.md Phase 21).
 */
export function ReviewedCandidatesTable({ section }: ReviewedCandidatesTableProps) {
  return (
    <div className="rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
      <div className="mb-1 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">검토한 대응안과 제외 사유</div>
      <div className="mb-3 text-[10.5px] text-[var(--text-tertiary)]">
        검토 {section.total_count}건 ㆍ 제외 {section.excluded_count}건
      </div>

      {section.candidates.length === 0 ? (
        <div className="rounded-md border border-dashed border-[var(--border-dashed)] px-3 py-3 text-[11px] text-[var(--text-secondary)]">
          검토한 대응안이 없습니다.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="border-b border-[var(--border)] text-[var(--text-tertiary)]">
                <th className="whitespace-nowrap px-2 py-1.5 font-semibold">대응안</th>
                <th className="whitespace-nowrap px-2 py-1.5 font-semibold">검증 상태</th>
                <th className="whitespace-nowrap px-2 py-1.5 font-semibold">제외 사유</th>
                <th className="whitespace-nowrap px-2 py-1.5 font-semibold">선행 조건</th>
              </tr>
            </thead>
            <tbody>
              {section.candidates.map((candidate) => (
                <tr key={candidate.candidate_id} className="border-b border-[var(--border)] last:border-b-0">
                  <td className="px-2 py-1.5">
                    <div className="font-bold text-[var(--text-primary)]">{candidate.candidate_type}</div>
                    <div className="text-[10.5px] text-[var(--text-secondary)]">{candidate.description}</div>
                  </td>
                  <td className="whitespace-nowrap px-2 py-1.5">
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${STATUS_COLOR[candidate.validation_status]}`}
                    >
                      {candidate.validation_status}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-[var(--text-secondary)]">{formatExclusion(candidate)}</td>
                  <td className="px-2 py-1.5 text-[var(--text-secondary)]">
                    {candidate.preconditions.length > 0 ? candidate.preconditions.join(", ") : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
