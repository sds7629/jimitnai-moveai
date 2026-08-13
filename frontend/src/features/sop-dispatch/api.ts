import { apiGet, apiPost } from "../../lib/apiClient";
import type { SopDispatchResultApi, SopStatusResponseApi } from "./types";

/** POST /approvals/{id}/dispatch-sop — 승인/조건부승인 + incident.status==='승인'일 때만 가능(멱등) */
export function dispatchSop(approvalId: number): Promise<SopDispatchResultApi[]> {
  return apiPost<SopDispatchResultApi[]>(`/approvals/${approvalId}/dispatch-sop`);
}

/** GET /incidents/{id}/sop-status */
export function getSopStatus(incidentId: number): Promise<SopStatusResponseApi> {
  return apiGet<SopStatusResponseApi>(`/incidents/${incidentId}/sop-status`);
}
