import type { DataAndDocumentsUsedSection, FactInferenceAssumptionSection } from "./types";

export interface EvidenceKeyValue {
  key: string;
  value: string;
}

export interface EvidenceCandidateRow {
  candidateId: string;
  referenceDocumentIds: string[];
  fact: EvidenceKeyValue[];
  inference: EvidenceKeyValue[];
  assumption: EvidenceKeyValue[];
}

/** fact/inference/assumption은 자유 형식 dict라, 값이 객체/배열이면 JSON 문자열로 펼친다 */
function toKeyValues(record: Record<string, unknown>): EvidenceKeyValue[] {
  return Object.entries(record).map(([key, value]) => ({
    key,
    value: typeof value === "object" && value !== null ? JSON.stringify(value) : String(value),
  }));
}

/**
 * 의사결정 근거 Phase 16 — data_and_documents_used의 참고 문서와
 * fact_inference_assumption을 후보 id 기준으로 병합해, "이 판단의 근거" 패널 하나로
 * 보여줄 수 있는 형태로 만든다.
 */
export function buildEvidenceCandidateRows(
  dataAndDocuments: DataAndDocumentsUsedSection,
  factInferenceAssumption: FactInferenceAssumptionSection,
): EvidenceCandidateRow[] {
  const candidateIds = new Set([
    ...Object.keys(dataAndDocuments.reference_document_ids_by_candidate ?? {}),
    ...Object.keys(factInferenceAssumption),
  ]);

  return Array.from(candidateIds)
    .sort((a, b) => Number(a) - Number(b))
    .map((candidateId) => {
      const entry = factInferenceAssumption[candidateId];
      return {
        candidateId,
        referenceDocumentIds: dataAndDocuments.reference_document_ids_by_candidate?.[candidateId] ?? [],
        fact: entry ? toKeyValues(entry.fact) : [],
        inference: entry ? toKeyValues(entry.inference) : [],
        assumption: entry ? toKeyValues(entry.assumption) : [],
      };
    });
}
