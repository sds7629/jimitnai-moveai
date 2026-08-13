import type { FeasibilityAndExclusionSection, KeySensitivityVariablesSection } from "./types";
import type { ExclusionCategory, ValidationStatus } from "../candidates/types";

export interface FeasibilityTableRow {
  candidateId: string;
  validationStatus: ValidationStatus;
  exclusionCategory: ExclusionCategory | null;
  exclusionDetail: string | null;
  preconditions: string[];
  sensitivityVariables: unknown[];
}

/**
 * 의사결정 근거 Phase 17 — feasibility_and_exclusion + key_sensitivity_variables를
 * 후보 id 기준으로 병합해 표 하나로 만든다. 민감도 변수는 시뮬레이션된 후보만 있어서
 * 없으면 빈 배열로 채운다.
 */
export function buildFeasibilityTable(
  feasibility: FeasibilityAndExclusionSection,
  sensitivity: KeySensitivityVariablesSection,
): FeasibilityTableRow[] {
  return Object.entries(feasibility)
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([candidateId, entry]) => ({
      candidateId,
      validationStatus: entry.validation_status,
      exclusionCategory: entry.exclusion_category,
      exclusionDetail: entry.exclusion_detail,
      preconditions: entry.preconditions,
      sensitivityVariables: sensitivity[candidateId] ?? [],
    }));
}
