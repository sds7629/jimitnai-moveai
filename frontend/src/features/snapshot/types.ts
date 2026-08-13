/**
 * GET /incidents/{id}/snapshots/latest 응답 타입.
 * backend/app/schemas/snapshot.py의 OperationalSnapshotRead를 그대로 옮겼다 (Phase 3).
 */
export interface OperationalSnapshotApi {
  id: number;
  incident_id: number;
  data_version: string;
  scenario_version: string;
  assumptions: string[];
  operational_state: Record<string, unknown>;
  /** "normal" | "limited" — simulation-supply-chain-tool.md §3.3 데이터 품질 게이트 */
  quality_mode: string;
  freshness_seconds: number | null;
  /** 0~1 사이 비율 */
  coverage_ratio: number | null;
  created_at: string;
}
