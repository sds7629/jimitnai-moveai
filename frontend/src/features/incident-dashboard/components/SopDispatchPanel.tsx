import type { SopStatusItemApi } from "../../sop-dispatch/types";

const STATUS_COLOR: Record<string, string> = {
  완료: "text-[var(--teal)]",
  실패: "text-[var(--red)]",
};

interface SopDispatchPanelProps {
  sopStatuses: SopStatusItemApi[];
}

/**
 * 승인 후 역할별(항만/운송/공장/영업/계약) SOP 발송 상태 패널.
 * POST /approvals/{id}/dispatch-sop로 승인 직후 자동 발송되고, GET /incidents/{id}/sop-status로
 * 현재 상태를 읽기 전용으로 보여준다 — 상태 전이(수신/수락/시작/진행/완료/실패)는 Phase 10에서
 * PATCH /sop/{sop_id}/status로 연결한다 (frontend/docs/FEATURE_PHASES.md Phase 9).
 */
export function SopDispatchPanel({ sopStatuses }: SopDispatchPanelProps) {
  return (
    <div className="rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
      <div className="mb-3 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">역할별 SOP 발송 상태</div>

      {sopStatuses.length === 0 && (
        <div className="rounded-md border border-dashed border-[var(--border-dashed)] px-3 py-3 text-[11px] text-[var(--text-secondary)]">
          아직 SOP가 발송되지 않았습니다. 승인/조건부승인이 기록되면 자동으로 발송됩니다.
        </div>
      )}

      {sopStatuses.map((item) => (
        <div key={item.sop_id} className="border-b border-[var(--border)] py-2.5 last:border-b-0">
          <div className="flex items-center justify-between">
            <div className="text-[12.5px] font-bold text-[var(--text-primary)]">{item.role ?? "담당자 미상"}</div>
            <div className={`text-[11px] font-semibold ${STATUS_COLOR[item.status] ?? "text-[var(--text-secondary)]"}`}>
              {item.status}
            </div>
          </div>
          {item.action_summary && (
            <div className="mt-1 text-[11px] text-[var(--text-secondary)]">{item.action_summary}</div>
          )}
        </div>
      ))}
    </div>
  );
}
