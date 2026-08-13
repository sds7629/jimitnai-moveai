import { apiGet } from "../../lib/apiClient";
import type { IncidentListItem } from "./types";

/** GET /incidents — 시드 3종(적체/파업/관세)을 포함한 사건 목록 조회 */
export function listIncidents(): Promise<IncidentListItem[]> {
  return apiGet<IncidentListItem[]>("/incidents");
}
