import { Link } from "react-router-dom";
import type { IncidentSummary } from "../types";

interface IncidentContextBarProps {
  incident: IncidentSummary;
  isRerunning?: boolean;
  /** POST /simulate가 실패했을 때 표시할 메시지 — 기존 화면 데이터는 그대로 유지한 채 알림만 띄운다 */
  rerunError?: string;
  /** 없으면 링크를 렌더링하지 않는다 (Phase 11 이전 호출부와의 호환) */
  postReportHref?: string;
  onRerun?: () => void;
}

/**
 * 사건 컨텍스트 바: 감지 뱃지, 사건명, 진행 배지, 사건 원문 입력창, 재실행 버튼, 사후보고서 링크.
 * "다시 실행"은 POST /incidents/{id}/simulate 재호출에 매핑된다 (Phase 5) — LLM 호출이 포함돼
 * 몇 초 걸릴 수 있어서 isRerunning 동안 버튼을 비활성화하고 진행 중 문구를 보여준다.
 */
export function IncidentContextBar({
  incident,
  isRerunning = false,
  rerunError,
  postReportHref,
  onRerun,
}: IncidentContextBarProps) {
  return (
    <div className="flex flex-col gap-1.5 border-b border-[var(--border)] px-7 py-3.5">
      <div className="flex items-center gap-3.5">
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
        {postReportHref && (
          <Link
            to={postReportHref}
            className="flex-shrink-0 whitespace-nowrap rounded-md border border-[var(--border-btn)] px-3.5 py-2.5 text-[13px] font-bold text-[var(--text-body)]"
          >
            사후보고서 보기
          </Link>
        )}
        <button
          type="button"
          onClick={onRerun}
          disabled={isRerunning}
          className="rounded-md bg-[var(--blue)] px-4.5 py-2.5 text-[13px] font-bold text-[var(--blue-text-on)] disabled:opacity-60"
        >
          {isRerunning ? "실행 중..." : "다시 실행"}
        </button>
      </div>
      {rerunError && <div className="text-[11px] text-[var(--red)]">재시뮬레이션 실패: {rerunError}</div>}
    </div>
  );
}
