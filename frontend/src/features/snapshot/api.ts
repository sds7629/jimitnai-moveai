import { apiGet } from "../../lib/apiClient";
import type { OperationalSnapshotApi } from "./types";

/** GET /incidents/{id}/snapshots/latest — DAG와 마찬가지로 lazy-create된다 */
export function getLatestSnapshot(incidentId: number): Promise<OperationalSnapshotApi> {
  return apiGet<OperationalSnapshotApi>(`/incidents/${incidentId}/snapshots/latest`);
}
