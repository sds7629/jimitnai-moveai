/**
 * POST /incidents/{id}/approvals 요청/응답 타입.
 * backend/app/schemas/approval.py를 그대로 옮겼다 (Phase 7).
 * '기한초과'는 시스템(check_deadline_overrun)만 기록할 수 있어 클라이언트가 보낼 수 있는 값이 아니다.
 */
export type ClientDecisionType = "승인" | "조건부승인" | "수정요청" | "반려";

export interface ApprovalCreateRequest {
  decision_type: ClientDecisionType;
  reason: string;
  approver: string;
}

/** 대시보드의 영문 ApprovalAction("approve" 등) → 백엔드 client_decision_type("승인" 등) 매핑 */
export const APPROVAL_ACTION_TO_DECISION_TYPE: Record<
  "approve" | "conditional" | "revise" | "reject",
  ClientDecisionType
> = {
  approve: "승인",
  conditional: "조건부승인",
  revise: "수정요청",
  reject: "반려",
};

export interface ApprovalApi {
  id: number;
  incident_id: number;
  decision_type: string;
  reason: string;
  approver: string;
  decided_at: string;
  data_version_ref: string | null;
  scenario_version_ref: string | null;
  created_at: string;
}
