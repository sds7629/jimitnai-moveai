import { useState } from "react";
import type { SopStatusItemApi } from "../../sop-dispatch/types";
import { VALID_SOP_TRANSITION_STATUSES, type SopTransitionStatus } from "../../execution-tracking/types";

const STATUS_COLOR: Record<string, string> = {
  완료: "text-[var(--teal)]",
  실패: "text-[var(--red)]",
};

interface SopDispatchPanelProps {
  sopStatuses: SopStatusItemApi[];
  isUpdating?: boolean;
  updateError?: string;
  onStatusUpdate?: (sopId: number, status: SopTransitionStatus, actor: string) => void;
}

/**
 * 승인 후 역할별(항만/운송/공장/영업/계약) SOP 발송 상태 패널.
 * POST /approvals/{id}/dispatch-sop로 승인 직후 자동 발송되고, GET /incidents/{id}/sop-status로
 * 현재 상태를 보여준다. 상태 전이(수신/수락/시작/진행/완료/실패)는 PATCH /sop/{sop_id}/status로
 * 연결한다 — 실행자는 모든 행이 공유하는 입력창 하나로 받는다(현장에서 한 사람이 여러 SOP를
 * 연속으로 갱신하는 경우가 흔하다고 가정) (frontend/docs/FEATURE_PHASES.md Phase 10).
 */
export function SopDispatchPanel({ sopStatuses, isUpdating = false, updateError, onStatusUpdate }: SopDispatchPanelProps) {
  const [actor, setActor] = useState("");
  const [validationError, setValidationError] = useState<string | undefined>(undefined);

  const handleClick = (sopId: number, status: SopTransitionStatus) => {
    const trimmedActor = actor.trim();
    if (!trimmedActor) {
      setValidationError("실행자를 입력해주세요");
      return;
    }
    setValidationError(undefined);
    onStatusUpdate?.(sopId, status, trimmedActor);
  };

  return (
    <div className="rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
      <div className="mb-3 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">역할별 SOP 발송 상태</div>

      {sopStatuses.length === 0 && (
        <div className="rounded-md border border-dashed border-[var(--border-dashed)] px-3 py-3 text-[11px] text-[var(--text-secondary)]">
          아직 SOP가 발송되지 않았습니다. 승인/조건부승인이 기록되면 자동으로 발송됩니다.
        </div>
      )}

      {sopStatuses.length > 0 && (
        <>
          <label className="mb-3 flex flex-col gap-1 text-[10.5px] text-[var(--text-secondary)]">
            실행자
            <input
              type="text"
              aria-label="실행자"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              disabled={isUpdating}
              className="rounded-md border border-[var(--border-input)] bg-[var(--panel-bg-2)] px-2.5 py-1.5 text-[12px] text-[var(--text-body)]"
            />
          </label>

          {validationError && <div className="mb-2 text-[10.5px] text-[var(--red)]">{validationError}</div>}
          {updateError && <div className="mb-2 text-[10.5px] text-[var(--red)]">상태 갱신 실패: {updateError}</div>}
        </>
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
          <div className="mt-2 flex flex-wrap gap-1.5">
            {VALID_SOP_TRANSITION_STATUSES.map((status) => (
              <button
                key={status}
                type="button"
                onClick={() => handleClick(item.sop_id, status)}
                disabled={isUpdating}
                className="rounded border border-[var(--border-btn)] px-2 py-1 text-[10px] text-[var(--text-body)] disabled:opacity-60"
              >
                {status}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
