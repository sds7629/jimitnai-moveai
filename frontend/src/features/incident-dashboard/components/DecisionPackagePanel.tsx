import { DECISION_PACKAGE_SECTIONS, type DecisionPackageApi } from "../../decision-package/types";
import type {
  ConfidenceAndUncertaintySection,
  ExpectedLossP90CvarSection,
} from "../../decision-package/types";
import { summarizeDeadline } from "../../decision-package/format";
import { buildExpectedLossTable } from "../../decision-package/expectedLossTable";
import { ExpectedLossTable } from "./ExpectedLossTable";

interface DecisionPackagePanelProps {
  decisionPackage: DecisionPackageApi;
  /** 테스트에서 시각을 고정하기 위한 주입 포인트. 기본값은 렌더링 시점의 현재 시각. */
  now?: Date;
}

/** Phase 13에서 전용 표로 옮긴 섹션 — 아래 일반 JSON 렌더링 목록에서는 제외한다 */
const TABLE_SECTION_KEYS = new Set(["expected_loss_p90_cvar", "confidence_and_uncertainty"]);

/**
 * 의사결정 근거 패널 — GET /incidents/{id}/decision-package 응답을 보여준다.
 *
 * simulation-supply-chain-tool.md §5.1의 10개 항목이 백엔드에 이미 전부 구현돼 있어서
 * (backend/app/services/response_optimization.py), 처음에는(Phase 6) 전부 "라벨 + JSON"으로
 * 일반화해서 배선만 했다. Phase 13부터 같은 표현 방식을 쓰는 섹션 묶음을 하나씩 전용 UI로
 * 바꾸는 중이다(frontend/docs/FEATURE_PHASES.md Phase 13~18) — 아직 안 바뀐 섹션은 여전히
 * JSON 그대로 보여준다.
 */
export function DecisionPackagePanel({ decisionPackage, now = new Date() }: DecisionPackagePanelProps) {
  const deadline = summarizeDeadline(decisionPackage.recommended_deadline, now);
  const expectedLossRows = buildExpectedLossTable(
    (decisionPackage.package.expected_loss_p90_cvar ?? {}) as ExpectedLossP90CvarSection,
    (decisionPackage.package.confidence_and_uncertainty ?? {}) as ConfidenceAndUncertaintySection,
  );

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

      <div className="border-b border-[var(--border)] py-2.5">
        <div className="mb-1 text-[11.5px] font-bold text-[var(--text-secondary-strong)]">
          기대손실·P90·CVaR·신뢰도
        </div>
        <ExpectedLossTable rows={expectedLossRows} />
      </div>

      {DECISION_PACKAGE_SECTIONS.filter(({ key }) => !TABLE_SECTION_KEYS.has(key)).map(({ key, label }) => (
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
