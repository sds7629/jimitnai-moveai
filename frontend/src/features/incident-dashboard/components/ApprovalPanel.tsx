import type { ApprovalAction } from "../types";

const ACTIONS: { action: ApprovalAction; label: string; variant: "primary" | "outline" | "danger" }[] = [
  { action: "approve", label: "승인", variant: "primary" },
  { action: "conditional", label: "조건부승인", variant: "outline" },
  { action: "revise", label: "수정요청", variant: "outline" },
  { action: "reject", label: "반려", variant: "danger" },
];

interface ApprovalPanelProps {
  onAction?: (action: ApprovalAction) => void;
}

/**
 * 승인 액션 패널.
 * simulation-supply-chain-tool.md §5.2 승인 분기(승인/조건부승인/수정요청/반려)에 대응 —
 * frontend/DAG_SCREEN_DESIGN_BRIEF.md §4에서 "확인되지 않음"으로 남겨뒀던 승인 액션이
 * 이후 와이어프레임에서 이 화면에 바로 포함되는 것으로 정리됐다.
 * 실제 클릭 시 POST /incidents/{id}/approvals 매핑은 백엔드 계약 확정 후 연결한다.
 */
export function ApprovalPanel({ onAction }: ApprovalPanelProps) {
  return (
    <div className="flex w-[230px] flex-shrink-0 flex-col gap-2.5 rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
      <div className="mb-0.5 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">승인 액션</div>
      {ACTIONS.map(({ action, label, variant }) => (
        <button
          key={action}
          type="button"
          onClick={() => onAction?.(action)}
          className={`rounded-md py-2.5 text-center text-[13px] font-bold ${
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
