import type { FeasibilityTableRow } from "../../decision-package/feasibilityTable";
import type { ValidationStatus } from "../../candidates/types";

/** candidates 랭킹의 후보 순번 뱃지(border-[var(--blue)])와 톤을 맞추되, 상태별로 색을 구분한다 */
const STATUS_COLOR: Record<ValidationStatus, string> = {
  가능: "border-[var(--teal)] text-[var(--teal)]",
  조건부: "border-[var(--amber)] text-[var(--amber)]",
  불가능: "border-[var(--red)] text-[var(--red)]",
  미검증: "border-[var(--border-mid)] text-[var(--text-secondary)]",
};

interface FeasibilityTableProps {
  rows: FeasibilityTableRow[];
}

/**
 * 의사결정 근거 Phase 17 — feasibility_and_exclusion + key_sensitivity_variables를
 * 후보별 실행 가능성 표로 렌더링한다 (frontend/docs/FEATURE_PHASES.md Phase 17).
 */
export function FeasibilityTable({ rows }: FeasibilityTableProps) {
  if (rows.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-[var(--border-dashed)] px-3 py-3 text-[11px] text-[var(--text-secondary)]">
        검증된 후보가 없습니다.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[11px]">
        <thead>
          <tr className="border-b border-[var(--border)] text-[var(--text-tertiary)]">
            <th className="whitespace-nowrap px-2 py-1.5 font-semibold">후보</th>
            <th className="whitespace-nowrap px-2 py-1.5 font-semibold">검증 상태</th>
            <th className="whitespace-nowrap px-2 py-1.5 font-semibold">제외 사유</th>
            <th className="whitespace-nowrap px-2 py-1.5 font-semibold">선행 조건</th>
            <th className="whitespace-nowrap px-2 py-1.5 font-semibold">민감도 변수</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.candidateId} className="border-b border-[var(--border)] last:border-b-0">
              <td className="whitespace-nowrap px-2 py-1.5 font-bold text-[var(--text-primary)]">{row.candidateId}</td>
              <td className="whitespace-nowrap px-2 py-1.5">
                <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${STATUS_COLOR[row.validationStatus]}`}>
                  {row.validationStatus}
                </span>
              </td>
              <td className="px-2 py-1.5 text-[var(--text-secondary)]">
                {row.exclusionCategory ? `${row.exclusionCategory} ㆍ ${row.exclusionDetail ?? ""}` : "-"}
              </td>
              <td className="px-2 py-1.5 text-[var(--text-secondary)]">
                {row.preconditions.length > 0 ? row.preconditions.join(", ") : "-"}
              </td>
              <td className="px-2 py-1.5 text-[var(--text-secondary)]">
                {row.sensitivityVariables.length > 0 ? row.sensitivityVariables.map((v) => String(v)).join(", ") : "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
