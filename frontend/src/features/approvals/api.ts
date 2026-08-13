import { apiPost } from "../../lib/apiClient";
import type { ApprovalApi, ApprovalCreateRequest } from "./types";

/** POST /incidents/{id}/approvals */
export function submitApproval(incidentId: number, request: ApprovalCreateRequest): Promise<ApprovalApi> {
  return apiPost<ApprovalApi>(`/incidents/${incidentId}/approvals`, request);
}
