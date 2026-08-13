import { DECISION_PACKAGE_SECTIONS, type DecisionPackageApi } from "../../decision-package/types";
import { summarizeDeadline } from "../../decision-package/format";

interface DecisionPackagePanelProps {
  decisionPackage: DecisionPackageApi;
  /** 테스트에서 시각을 고정하기 위한 주입 포인트. 기본값은 렌더링 시점의 현재 시각. */
  now?: Date;
}

/**
 * 의사결정 근거 패널 — GET /incidents/{id}/decision-package 응답을 그대로 펼쳐서 보여준다.
 *
 * simulation-supply-chain-tool.md §5.1의 10개 항목이 백엔드에 이미 전부 구현돼 있어서
 * (backend/app/services/response_optimization.py), 프론트는 각 섹션을 읽기 쉬운 형태로
 * 나열하는 역할만 한다 — 백엔드도 이 blob을 의도적으로 dict[str, Any]로 유지하므로, 프론트도
 * 섹션별로 억지로 세분화된 컴포넌트를 만들지 않고 일반화된 렌더링으로 대응한다
 * (frontend/docs/FEATURE_PHASES.md Phase 6).
 */
export function DecisionPackagePanel({ decisionPackage, now = new Date() }: DecisionPackagePanelProps) {
  const deadline = summarizeDeadline(decisionPackage.recommended_deadline, now);

  return (
    <div className="rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
      <div className="mb-1 flex items-center justify-between">
        <div className="text-[13.5px] font-bold text-[var(--text-secondary-strong)]">의사결정 근거</div>
        <div
          className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
            deadline.overdue
              ? "border-[var(--red-border-strong)] text-[var(--red)]"
              : "border-[var(--border-mid)] text-[var(--text-secondary)]"
          }`}
        >
          결정기한 {deadline.label}
        </div>
      </div>
      <div className="mb-3 text-[10.5px] text-[var(--text-tertiary)]">{String(decisionPackage.package.disclaimer ?? "")}</div>

      {DECISION_PACKAGE_SECTIONS.map(({ key, label }) => (
        <div key={key} className="border-b border-[var(--border)] py-2.5 last:border-b-0">
          <div className="mb-1 text-[11.5px] font-bold text-[var(--text-secondary-strong)]">{label}</div>
          <pre className="whitespace-pre-wrap break-words rounded bg-[var(--panel-bg-2)] p-2 text-[10px] leading-relaxed text-[var(--text-secondary)]">
            {JSON.stringify(decisionPackage.package[key] ?? null, null, 2)}
          </pre>
        </div>
      ))}
    </div>
  );
}
