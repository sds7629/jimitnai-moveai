import { apiGet } from "../../lib/apiClient";
import type { CostAttributionApi, PostReportApi } from "./types";

/** GET /incidents/{id}/post-report — 매번 재계산(별도 저장 테이블 없음), LLM 호출 없음 */
export function getPostReport(incidentId: number): Promise<PostReportApi> {
  return apiGet<PostReportApi>(`/incidents/${incidentId}/post-report`);
}

/** GET /incidents/{id}/cost-attribution */
export function getCostAttribution(incidentId: number): Promise<CostAttributionApi> {
  return apiGet<CostAttributionApi>(`/incidents/${incidentId}/cost-attribution`);
}
