import { apiGet, apiPost } from "../../lib/apiClient";
import type { CandidatesListResponse, SimulatePipelineResponse } from "./types";

/** GET /incidents/{id}/candidates — 읽기 전용, lazy-create하지 않는다(POST /simulate가 있어야 채워짐) */
export function listCandidates(incidentId: number): Promise<CandidatesListResponse> {
  return apiGet<CandidatesListResponse>(`/incidents/${incidentId}/candidates`);
}

/** POST /incidents/{id}/simulate — 대응안 생성(최초 1회)→제약검증→LLM 시뮬레이션 파이프라인 실행 */
export function runSimulation(incidentId: number): Promise<SimulatePipelineResponse> {
  return apiPost<SimulatePipelineResponse>(`/incidents/${incidentId}/simulate`);
}
