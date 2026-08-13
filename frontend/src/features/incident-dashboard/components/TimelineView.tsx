import type { TimelineEventApi } from "../../execution-tracking/types";

interface TimelineViewProps {
  events: TimelineEventApi[];
}

/**
 * 실행 추적 타임라인 — GET /incidents/{id}/timeline의 audit_log 이벤트를 그대로 나열한다.
 * is_deviation_event=true인 항목(계획 대비 편차/에스컬레이션)은 경고 스타일로 강조한다
 * (frontend/docs/FEATURE_PHASES.md Phase 10).
 */
export function TimelineView({ events }: TimelineViewProps) {
  if (events.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-[var(--border-dashed)] px-3 py-3 text-[11px] text-[var(--text-secondary)]">
        타임라인이 아직 없습니다.
      </div>
    );
  }

  return (
    <ol className="flex flex-col gap-2">
      {events.map((event) => (
        <li
          key={event.id}
          className={`rounded-md border px-3 py-2 text-[11px] ${
            event.is_deviation_event
              ? "border-[var(--red-border)] bg-[var(--red-chip-bg)]"
              : "border-[var(--border)] bg-[var(--panel-bg-2)]"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="font-semibold text-[var(--text-primary)]">
              {event.is_deviation_event && "⚠ 편차 · "}
              {event.event_type}
            </span>
            <span className="text-[var(--text-tertiary)]">
              {new Date(event.created_at).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" })}
            </span>
          </div>
          <div className="mt-0.5 text-[var(--text-secondary)]">
            {event.actor}
            {event.reason && ` — ${event.reason}`}
          </div>
        </li>
      ))}
    </ol>
  );
}
