import { apiGet, apiPatch } from "../../lib/apiClient";
import type { SopStatusTransitionApi, SopStatusUpdateRequest, TimelineResponseApi } from "./types";

/** PATCH /sop/{sop_id}/status — 편차 감지 시 서버가 재시뮬레이션까지 트리거할 수 있어 응답이 늦을 수 있다 */
export function updateSopStatus(sopId: number, request: SopStatusUpdateRequest): Promise<SopStatusTransitionApi> {
  return apiPatch<SopStatusTransitionApi>(`/sop/${sopId}/status`, request);
}

/** GET /incidents/{id}/timeline */
export function getTimeline(incidentId: number): Promise<TimelineResponseApi> {
  return apiGet<TimelineResponseApi>(`/incidents/${incidentId}/timeline`);
}
