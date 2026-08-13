import type {
  DataAndDocumentsUsedSection,
  FactInferenceAssumptionSection,
  FreshnessAndCoverageSection,
} from "../../decision-package/types";
import { buildEvidenceCandidateRows, type EvidenceKeyValue } from "../../decision-package/evidencePanel";
import { formatCoverage, formatFreshness, formatQualityMode } from "../../snapshot/format";

function KeyValueList({ label, items }: { label: string; items: EvidenceKeyValue[] }) {
  if (items.length === 0) return null;
  return (
    <div className="mt-1.5">
      <span className="rounded bg-[var(--blue-chip-bg)] px-1.5 py-0.5 text-[9.5px] font-bold text-[var(--blue)]">
        {label}
      </span>
      <div className="mt-1 text-[10.5px] leading-relaxed text-[var(--text-secondary)]">
        {items.map(({ key, value }) => (
          <div key={key}>
            {key}: {value}
          </div>
        ))}
      </div>
    </div>
  );
}

interface EvidencePanelProps {
  dataAndDocuments: DataAndDocumentsUsedSection;
  factInferenceAssumption: FactInferenceAssumptionSection;
  freshnessAndCoverage: FreshnessAndCoverageSection;
}

/**
 * 의사결정 근거 Phase 16 — data_and_documents_used + fact_inference_assumption +
 * freshness_and_coverage를 "이 판단의 근거" 패널 하나로 통합해 보여준다
 * (frontend/docs/FEATURE_PHASES.md Phase 16). freshness/coverage 문구는 Phase 3의
 * summarizeSnapshot과 같은 포맷 함수를 재사용해 화면 표현을 통일한다.
 */
export function EvidencePanel({ dataAndDocuments, factInferenceAssumption, freshnessAndCoverage }: EvidencePanelProps) {
  const rows = buildEvidenceCandidateRows(dataAndDocuments, factInferenceAssumption);

  return (
    <div>
      <div className="flex flex-wrap gap-1.5">
        <span className="rounded-full border border-[var(--border-mid)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
          {formatQualityMode(freshnessAndCoverage.quality_mode)}
        </span>
        <span className="rounded-full border border-[var(--border-mid)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
          최신성 {formatFreshness(freshnessAndCoverage.freshness_seconds)}
        </span>
        <span className="rounded-full border border-[var(--border-mid)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
          커버리지 {formatCoverage(freshnessAndCoverage.coverage_ratio)}
        </span>
      </div>

      <div className="mt-2 text-[10.5px] text-[var(--text-tertiary)]">
        데이터 버전 {dataAndDocuments.data_version} · 시나리오 버전 {dataAndDocuments.scenario_version}
      </div>

      <div className="mt-2">
        <div className="mb-1 text-[10.5px] font-bold text-[var(--text-secondary-strong)]">가정</div>
        {dataAndDocuments.operational_assumptions.length === 0 ? (
          <div className="text-[10.5px] text-[var(--text-secondary)]">등록된 가정이 없습니다.</div>
        ) : (
          <ul className="list-disc pl-4 text-[10.5px] text-[var(--text-secondary)]">
            {dataAndDocuments.operational_assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        )}
      </div>

      {rows.length > 0 && (
        <div className="mt-3 flex flex-col gap-2">
          {rows.map((row) => (
            <div key={row.candidateId} className="rounded-md border border-[var(--border)] bg-[var(--panel-bg-2)] p-2.5">
              <div className="text-[10.5px] font-bold text-[var(--text-secondary-strong)]">후보 {row.candidateId}</div>
              {row.referenceDocumentIds.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {row.referenceDocumentIds.map((docId) => (
                    <span
                      key={docId}
                      className="rounded bg-[var(--panel-bg)] px-1.5 py-0.5 text-[9.5px] text-[var(--text-tertiary)]"
                    >
                      {docId}
                    </span>
                  ))}
                </div>
              )}
              <KeyValueList label="FACT" items={row.fact} />
              <KeyValueList label="INFERENCE" items={row.inference} />
              <KeyValueList label="ASSUMPTION" items={row.assumption} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
