import { useState } from "react";
import type { ApprovalAction } from "../types";

const ACTIONS: { action: ApprovalAction; label: string; variant: "primary" | "outline" | "danger" }[] = [
  { action: "approve", label: "승인", variant: "primary" },
  { action: "conditional", label: "조건부승인", variant: "outline" },
  { action: "revise", label: "수정요청", variant: "outline" },
  { action: "reject", label: "반려", variant: "danger" },
];

/** backend/app/schemas/approval.py CONDITIONAL_APPROVAL_MIN_REASON_LENGTH와 동일 — 서버 검증과
 * 같은 기준으로 클라이언트에서 먼저 걸러 왕복 없이 피드백한다 */
const CONDITIONAL_APPROVAL_MIN_REASON_LENGTH = 10;

interface ApprovalPanelProps {
  isSubmitting?: boolean;
  submitError?: string;
  onSubmit?: (action: ApprovalAction, reason: string, approver: string) => void;
}

/**
 * 승인 액션 패널.
 * simulation-supply-chain-tool.md §5.2 승인 분기(승인/조건부승인/수정요청/반려)에 대응하며,
 * POST /incidents/{id}/approvals가 요구하는 reason/approver 입력 폼을 포함한다 (Phase 7).
 * 조건부승인은 서버가 사유 10자 미만이면 거부하므로 동일 기준을 클라이언트에서도 먼저 검증한다.
 */
export function ApprovalPanel({ isSubmitting = false, submitError, onSubmit }: ApprovalPanelProps) {
  const [reason, setReason] = useState("");
  const [approver, setApprover] = useState("");
  const [validationError, setValidationError] = useState<string | undefined>(undefined);

  const handleClick = (action: ApprovalAction) => {
    const trimmedReason = reason.trim();
    const trimmedApprover = approver.trim();

    if (!trimmedApprover) {
      setValidationError("승인자를 입력해주세요");
      return;
    }
    if (!trimmedReason) {
      setValidationError("사유를 입력해주세요");
      return;
    }
    if (action === "conditional" && trimmedReason.length < CONDITIONAL_APPROVAL_MIN_REASON_LENGTH) {
      setValidationError(`조건부승인은 사유를 ${CONDITIONAL_APPROVAL_MIN_REASON_LENGTH}자 이상 구체적으로 입력해야 합니다`);
      return;
    }

    setValidationError(undefined);
    onSubmit?.(action, trimmedReason, trimmedApprover);
  };

  return (
    <div className="flex w-[230px] flex-shrink-0 flex-col gap-2.5 rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
      <div className="mb-0.5 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">승인 액션</div>

      <label className="flex flex-col gap-1 text-[10.5px] text-[var(--text-secondary)]">
        승인자
        <input
          type="text"
          aria-label="승인자"
          value={approver}
          onChange={(e) => setApprover(e.target.value)}
          disabled={isSubmitting}
          className="rounded-md border border-[var(--border-input)] bg-[var(--panel-bg-2)] px-2.5 py-1.5 text-[12px] text-[var(--text-body)]"
        />
      </label>

      <label className="flex flex-col gap-1 text-[10.5px] text-[var(--text-secondary)]">
        사유
        <textarea
          aria-label="사유"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          disabled={isSubmitting}
          rows={3}
          className="rounded-md border border-[var(--border-input)] bg-[var(--panel-bg-2)] px-2.5 py-1.5 text-[12px] text-[var(--text-body)]"
        />
      </label>

      {validationError && <div className="text-[10.5px] text-[var(--red)]">{validationError}</div>}
      {submitError && <div className="text-[10.5px] text-[var(--red)]">제출 실패: {submitError}</div>}

      {ACTIONS.map(({ action, label, variant }) => (
        <button
          key={action}
          type="button"
          onClick={() => handleClick(action)}
          disabled={isSubmitting}
          className={`rounded-md py-2.5 text-center text-[13px] font-bold disabled:opacity-60 ${
            variant === "primary"
              ? "bg-[var(--blue)] text-[var(--blue-text-on)]"
              : variant === "danger"
                ? "border border-[var(--red-border-strong)] text-[var(--red)]"
                : "border border-[var(--border-btn)] text-[var(--text-body)]"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
