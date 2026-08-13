/**
 * PATCH /sop/{sop_id}/status, GET /incidents/{id}/timeline 요청/응답 타입.
 * backend/app/schemas/execution_tracking.py를 그대로 옮겼다 (Phase 10).
 */
export type SopTransitionStatus = "수신" | "수락" | "시작" | "진행" | "완료" | "실패";

export const VALID_SOP_TRANSITION_STATUSES: readonly SopTransitionStatus[] = [
  "수신",
  "수락",
  "시작",
  "진행",
  "완료",
  "실패",
];

export interface SopStatusUpdateRequest {
  status: SopTransitionStatus;
  actor: string;
  note?: string;
}

export interface SopStatusTransitionApi {
  id: number;
  incident_id: number | null;
  sop_id: number;
  status: string;
  actor: string;
  note: string | null;
  created_at: string;
  /** 편차 감지·재평가가 트리거됐으면 그 결과, 아니면 null */
  deviation_check: Record<string, unknown> | null;
}

export interface TimelineEventApi {
  id: number;
  event_type: string;
  actor: string;
  reason: string | null;
  sop_id: number | null;
  status: string | null;
  payload: Record<string, unknown>;
  created_at: string;
  is_deviation_event: boolean;
}

export interface TimelineResponseApi {
  incident_id: number;
  events: TimelineEventApi[];
}
