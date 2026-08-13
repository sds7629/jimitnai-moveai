import { apiGet } from "../../lib/apiClient";
import type { ImpactDagApiResponse } from "./types";

/** GET /incidents/{id}/impact-dag — 스냅샷·DAG는 lazy-create되므로 최초 호출 시 백엔드가 생성한다 */
export function getImpactDag(incidentId: number): Promise<ImpactDagApiResponse> {
  return apiGet<ImpactDagApiResponse>(`/incidents/${incidentId}/impact-dag`);
}
