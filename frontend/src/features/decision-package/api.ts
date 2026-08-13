import { apiGet } from "../../lib/apiClient";
import type { DecisionPackageApi } from "./types";

/** GET /incidents/{id}/decision-package — 최신 시뮬레이션 이후면 새로 만들고, 아니면 기존 것을 재사용 */
export function getDecisionPackage(incidentId: number): Promise<DecisionPackageApi> {
  return apiGet<DecisionPackageApi>(`/incidents/${incidentId}/decision-package`);
}
