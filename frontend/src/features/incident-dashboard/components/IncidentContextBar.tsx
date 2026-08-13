import type { IncidentSummary } from "../types";

interface IncidentContextBarProps {
  incident: IncidentSummary;
  onRerun?: () => void;
}

/**
 * 사건 컨텍스트 바: 감지 뱃지, 사건명, 진행 배지, 사건 원문 입력창, 재실행 버튼.
 * "다시 실행"은 POST /incidents/{id}/simulate 재호출에 매핑된다
 * (frontend/DAG_SCREEN_DESIGN_BRIEF.md §7 인터랙션 매핑 참고).
 */
export function IncidentContextBar({ incident, onRerun }: IncidentContextBarProps) {
  return (
    <div className="flex items-center gap-3.5 border-b border-[var(--border)] px-7 py-3.5">
      <div className="flex-shrink-0 whitespace-nowrap rounded-full border border-[var(--red-border)] px-3 py-1 text-[11.5px] font-bold text-[var(--red)]">
        🔔 GVIS 감지
      </div>
      <div className="flex-shrink-0 whitespace-nowrap text-[16px] font-bold text-[var(--text-primary)]">
        {incident.name}
      </div>
      <div className="flex-shrink-0 whitespace-nowrap rounded-full border border-dashed border-[var(--border-dashed)] px-2.5 py-1 text-[11.5px] text-[var(--text-secondary)]">
        {incident.progressBadge}
      </div>
      <input
        type="text"
        placeholder={incident.rawTextPlaceholder}
        aria-label="사건 원문 입력"
        className="flex-1 rounded-md border border-[var(--border-input)] bg-[var(--panel-bg)] px-3.5 py-2 text-[12.5px] text-[var(--text-body)] placeholder:text-[var(--text-tertiary)] focus:outline-none"
      />
      <button
        type="button"
        onClick={onRerun}
        className="rounded-md bg-[var(--blue)] px-4.5 py-2.5 text-[13px] font-bold text-[var(--blue-text-on)]"
      >
        다시 실행
      </button>
    </div>
  );
}
