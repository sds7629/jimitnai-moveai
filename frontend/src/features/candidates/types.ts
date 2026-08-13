/**
 * POST /incidents/{id}/simulate, GET /incidents/{id}/candidates 응답 타입.
 * backend/app/schemas/simulate.py를 그대로 옮겼다 — 실제 응답 필드 확인 완료
 * (frontend/docs/FEATURE_PHASES.md Phase 5).
 */

/** backend/app/services/constraint_validation.py에서 확인된 실제 값 */
export type ValidationStatus = "미검증" | "가능" | "조건부" | "불가능";

/** backend/app/services/constraint_validation.py EXCLUSION_CATEGORIES */
export type ExclusionCategory = "자원부족" | "기한불가" | "예산초과" | "계약위반";

export interface SimulationResultApi {
  id: number;
  candidate_id: number;
  incident_id: number;
  expected_loss: number | null;
  p90: number | null;
  cvar: number | null;
  sensitivity_variables: unknown[];
  confidence: number | null;
  fact: Record<string, unknown>;
  inference: Record<string, unknown>;
  assumption: Record<string, unknown>;
  data_version: string;
  scenario_version: string;
  created_at: string;
}

export interface CandidateApi {
  id: number;
  incident_id: number;
  snapshot_id: number;
  candidate_type: string;
  description: string;
  reference_document_ids: unknown[];
  preconditions: string[];
  start_time_variant: string | null;
  validation_status: ValidationStatus;
  exclusion_category: ExclusionCategory | null;
  exclusion_detail: string | null;
  created_at: string;
  updated_at: string;
  latest_simulation: SimulationResultApi | null;
}

export interface CandidatesListResponse {
  incident_id: number;
  candidates: CandidateApi[];
}

export interface SimulatePipelineResponse {
  incident_id: number;
  reused_existing_candidates: boolean;
  candidate_count: number;
  validated_count: number;
  simulated_count: number;
}

export const BASELINE_CANDIDATE_TYPE = "baseline";
