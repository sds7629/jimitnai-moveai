/**
 * POST /approvals/{id}/dispatch-sop, GET /incidents/{id}/sop-status 응답 타입.
 * backend/app/schemas/sop_dispatch.py를 그대로 옮겼다 (Phase 9).
 */
export interface SopDispatchResultApi {
  sop_id: number;
  incident_id: number | null;
  role: string | null;
  approval_id: number | null;
  dispatched_at: string;
  action: string | null;
  message_text: string | null;
}

export interface SopStatusEventApi {
  event_type: string;
  actor: string;
  reason: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

/** backend/app/services/execution_tracking.py VALID_SOP_STATUSES */
export type SopStatus = "발송" | "수신" | "수락" | "시작" | "진행" | "완료" | "실패";

export interface SopStatusItemApi {
  sop_id: number;
  incident_id: number;
  role: string | null;
  approval_id: number | null;
  action_summary: string | null;
  dispatched_at: string;
  dispatched_by: string;
  status: string;
  received_at: string | null;
  accepted_at: string | null;
  completed_at: string | null;
  failed_at: string | null;
  events: SopStatusEventApi[];
}

export interface SopStatusResponseApi {
  incident_id: number;
  sop_statuses: SopStatusItemApi[];
}
