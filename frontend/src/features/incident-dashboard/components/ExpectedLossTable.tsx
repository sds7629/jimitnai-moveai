import type { ExpectedLossTableRow } from "../../decision-package/expectedLossTable";

interface ExpectedLossTableProps {
  rows: ExpectedLossTableRow[];
}

const COLUMNS: { key: keyof ExpectedLossTableRow; label: string }[] = [
  { key: "candidateType", label: "대응안" },
  { key: "expectedLoss", label: "기대손실" },
  { key: "p90", label: "P90" },
  { key: "cvar", label: "CVaR" },
  { key: "confidencePercent", label: "신뢰도" },
  { key: "p90MinusExpectedLoss", label: "P90-기대손실" },
  { key: "cvarMinusP90", label: "CVaR-P90" },
];

/**
 * 의사결정 근거 Phase 13 — expected_loss_p90_cvar + confidence_and_uncertainty를 후보별 표로.
 * frontend/docs/FEATURE_PHASES.md Phase 13.
 */
export function ExpectedLossTable({ rows }: ExpectedLossTableProps) {
  if (rows.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-[var(--border-dashed)] px-3 py-3 text-[11px] text-[var(--text-secondary)]">
        시뮬레이션된 후보가 없습니다.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[11px]">
        <thead>
          <tr className="border-b border-[var(--border)] text-[var(--text-tertiary)]">
            {COLUMNS.map(({ key, label }) => (
              <th key={key} className="whitespace-nowrap px-2 py-1.5 font-semibold">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.candidateId} className="border-b border-[var(--border)] last:border-b-0">
              <td className="whitespace-nowrap px-2 py-1.5 font-bold text-[var(--text-primary)]">
                {row.candidateType}
              </td>
              <td className="whitespace-nowrap px-2 py-1.5">{row.expectedLoss}</td>
              <td className="whitespace-nowrap px-2 py-1.5">{row.p90}</td>
              <td className="whitespace-nowrap px-2 py-1.5">{row.cvar}</td>
              <td className="whitespace-nowrap px-2 py-1.5">
                {row.confidencePercent !== null ? `${row.confidencePercent}%` : "-"}
              </td>
              <td className="whitespace-nowrap px-2 py-1.5 text-[var(--text-secondary)]">
                {row.p90MinusExpectedLoss}
              </td>
              <td className="whitespace-nowrap px-2 py-1.5 text-[var(--text-secondary)]">{row.cvarMinusP90}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
