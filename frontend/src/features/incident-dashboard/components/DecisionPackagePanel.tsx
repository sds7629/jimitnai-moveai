import { DECISION_PACKAGE_SECTIONS, type DecisionPackageApi } from "../../decision-package/types";
import type {
  CausalPathSection,
  ConfidenceAndUncertaintySection,
  DataAndDocumentsUsedSection,
  ExpectedLossP90CvarSection,
  FactInferenceAssumptionSection,
  FeasibilityAndExclusionSection,
  FreshnessAndCoverageSection,
  KeySensitivityVariablesSection,
  NowVs6hVsNoActionSection,
} from "../../decision-package/types";
import { summarizeDeadline } from "../../decision-package/format";
import { buildExpectedLossTable } from "../../decision-package/expectedLossTable";
import { buildFeasibilityTable } from "../../decision-package/feasibilityTable";
import { ExpectedLossTable } from "./ExpectedLossTable";
import { NowVs6hComparison } from "./NowVs6hComparison";
import { CausalPathList } from "./CausalPathList";
import { EvidencePanel } from "./EvidencePanel";
import { FeasibilityTable } from "./FeasibilityTable";

interface DecisionPackagePanelProps {
  decisionPackage: DecisionPackageApi;
  /** 테스트에서 시각을 고정하기 위한 주입 포인트. 기본값은 렌더링 시점의 현재 시각. */
  now?: Date;
}

/** Phase 13~14에서 전용 UI로 옮긴 섹션 — 아래 일반 JSON 렌더링 목록에서는 제외한다 */
const MIGRATED_SECTION_KEYS = new Set([
  "expected_loss_p90_cvar",
  "confidence_and_uncertainty",
  "now_vs_6h_vs_no_action",
  "causal_path",
  "data_and_documents_used",
  "fact_inference_assumption",
  "freshness_and_coverage",
  "feasibility_and_exclusion",
  "key_sensitivity_variables",
]);

const EMPTY_NOW_VS_6H: NowVs6hVsNoActionSection = { no_action: null, now: null, plus_6h: null };
const EMPTY_CAUSAL_PATH: CausalPathSection = { nodes: [], edges: [] };
const EMPTY_DATA_AND_DOCUMENTS: DataAndDocumentsUsedSection = {
  operational_assumptions: [],
  data_version: "-",
  scenario_version: "-",
  reference_document_ids_by_candidate: {},
};
const EMPTY_FRESHNESS_AND_COVERAGE: FreshnessAndCoverageSection = {
  quality_mode: "-",
  freshness_seconds: null,
  coverage_ratio: null,
};

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
  const nowVs6h = (decisionPackage.package.now_vs_6h_vs_no_action ?? EMPTY_NOW_VS_6H) as NowVs6hVsNoActionSection;
  // 백엔드 blob이 loosely-typed dict라 causal_path 자체는 있어도 nodes/edges 키가 빠질 수 있다
  // (예: 목업 fixture의 causal_path: {}) — Phase 14의 undefined 버그와 같은 패턴이라 각 필드를
  // 개별적으로 기본값 처리한다.
  const rawCausalPath = (decisionPackage.package.causal_path ?? {}) as Partial<CausalPathSection>;
  const causalPath: CausalPathSection = {
    nodes: rawCausalPath.nodes ?? EMPTY_CAUSAL_PATH.nodes,
    edges: rawCausalPath.edges ?? EMPTY_CAUSAL_PATH.edges,
  };
  const rawDataAndDocuments = (decisionPackage.package.data_and_documents_used ?? {}) as Partial<DataAndDocumentsUsedSection>;
  const dataAndDocuments: DataAndDocumentsUsedSection = {
    operational_assumptions: rawDataAndDocuments.operational_assumptions ?? EMPTY_DATA_AND_DOCUMENTS.operational_assumptions,
    data_version: rawDataAndDocuments.data_version ?? EMPTY_DATA_AND_DOCUMENTS.data_version,
    scenario_version: rawDataAndDocuments.scenario_version ?? EMPTY_DATA_AND_DOCUMENTS.scenario_version,
    reference_document_ids_by_candidate:
      rawDataAndDocuments.reference_document_ids_by_candidate ?? EMPTY_DATA_AND_DOCUMENTS.reference_document_ids_by_candidate,
  };
  const factInferenceAssumption = (decisionPackage.package.fact_inference_assumption ??
    {}) as FactInferenceAssumptionSection;
  // freshness_and_coverage도 causal_path와 같은 이유(키 자체가 빠진 {} 형태의 fixture가
  // 실제로 존재함)로 필드별 기본값 처리한다 — 통째로 ?? 하면 {}는 truthy라 기본값이 적용되지
  // 않아 quality_mode/freshness_seconds/coverage_ratio가 undefined인 채로 NaN%처럼 잘못 표시된다.
  const rawFreshnessAndCoverage = (decisionPackage.package.freshness_and_coverage ?? {}) as Partial<FreshnessAndCoverageSection>;
  const freshnessAndCoverage: FreshnessAndCoverageSection = {
    quality_mode: rawFreshnessAndCoverage.quality_mode ?? EMPTY_FRESHNESS_AND_COVERAGE.quality_mode,
    freshness_seconds: rawFreshnessAndCoverage.freshness_seconds ?? EMPTY_FRESHNESS_AND_COVERAGE.freshness_seconds,
    coverage_ratio: rawFreshnessAndCoverage.coverage_ratio ?? EMPTY_FRESHNESS_AND_COVERAGE.coverage_ratio,
  };
  const feasibilityRows = buildFeasibilityTable(
    (decisionPackage.package.feasibility_and_exclusion ?? {}) as FeasibilityAndExclusionSection,
    (decisionPackage.package.key_sensitivity_variables ?? {}) as KeySensitivityVariablesSection,
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

      <div className="border-b border-[var(--border)] py-2.5">
        <div className="mb-1 text-[11.5px] font-bold text-[var(--text-secondary-strong)]">
          지금 대응 vs 6시간 후 대응 vs 무대응
        </div>
        <NowVs6hComparison section={nowVs6h} />
      </div>

      <div className="border-b border-[var(--border)] py-2.5">
        <div className="mb-1 text-[11.5px] font-bold text-[var(--text-secondary-strong)]">영향 전파 경로</div>
        <CausalPathList section={causalPath} />
      </div>

      <div className="border-b border-[var(--border)] py-2.5">
        <div className="mb-1 text-[11.5px] font-bold text-[var(--text-secondary-strong)]">이 판단의 근거</div>
        <EvidencePanel
          dataAndDocuments={dataAndDocuments}
          factInferenceAssumption={factInferenceAssumption}
          freshnessAndCoverage={freshnessAndCoverage}
        />
      </div>

      <div className="border-b border-[var(--border)] py-2.5">
        <div className="mb-1 text-[11.5px] font-bold text-[var(--text-secondary-strong)]">실행 가능성·제외 사유</div>
        <FeasibilityTable rows={feasibilityRows} />
      </div>

      {DECISION_PACKAGE_SECTIONS.filter(({ key }) => !MIGRATED_SECTION_KEYS.has(key)).map(({ key, label }) => (
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
