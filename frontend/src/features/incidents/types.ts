/**
 * GET /incidents 응답 타입.
 * backend/app/schemas/incident.py의 IncidentListItem을 그대로 옮겼다 — 실제 응답 필드 확인 완료.
 */
export interface IncidentListItem {
  id: number;
  type: string;
  location: string;
  occurred_at: string;
  status: string;
  duplicate_of_incident_id: number | null;
  created_at: string;
}
