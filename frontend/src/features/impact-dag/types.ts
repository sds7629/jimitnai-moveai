/**
 * GET /incidents/{id}/impact-dag 응답 타입.
 * backend/app/schemas/impact_dag.py를 그대로 옮겼다 — 실제 응답 필드 확인 완료
 * (frontend/docs/FEATURE_PHASES.md Phase 2).
 */
export interface ImpactDagNodeApi {
  id: number;
  snapshot_id: number;
  node_key: string;
  label: string;
  affected_target: string | null;
  expected_time: string | null;
  basis: string | null;
  responsible_party: string | null;
  uncertainty: string | null;
  created_at: string;
}

export interface ImpactDagEdgeApi {
  id: number;
  snapshot_id: number;
  from_node_id: number;
  to_node_id: number;
  basis: string | null;
  created_at: string;
}

export interface ImpactDagApiResponse {
  incident_id: number;
  snapshot_id: number;
  data_version: string;
  scenario_version: string;
  quality_mode: string;
  nodes: ImpactDagNodeApi[];
  edges: ImpactDagEdgeApi[];
}
