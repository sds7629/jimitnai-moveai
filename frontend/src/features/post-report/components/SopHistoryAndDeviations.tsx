import { TimelineView } from "../../incident-dashboard/components/TimelineView";
import type { DeviationHistorySection, SopHistorySection } from "../types";

/** incident-dashboard의 SopDispatchPanel과 같은 완료/실패 색 구분 — 두 화면의 톤을 맞춘다 */
const STATUS_COLOR: Record<string, string> = {
  완료: "border-[var(--teal)] text-[var(--teal)]",
  실패: "border-[var(--red)] text-[var(--red)]",
};

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

interface SopHistoryAndDeviationsProps {
  sopHistory: SopHistorySection;
  deviationHistory: DeviationHistorySection;
}

/**
 * 사후보고서 Phase 22 — sections["6_SOP_발송_수신_수락_실행_이력"] +
 * sections["11_자원_확보_실패_실행_편차와_에스컬레이션_이력"]를 조회용 카드로 렌더링한다
 * (frontend/docs/FEATURE_PHASES.md Phase 22).
 *
 * 대시보드의 SopDispatchPanel과 달리 여긴 사후 리포트라 상태 전이 버튼/입력창 같은
 * 액션 UI는 넣지 않는다 — 발송 이력을 그대로 나열하는 순수 조회용 뷰다.
 */
export function SopHistoryAndDeviations({ sopHistory, deviationHistory }: SopHistoryAndDeviationsProps) {
  return (
    <div className="flex flex-col gap-5">
      <div className="rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
        <div className="mb-1 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">
          SOP 발송·수신·수락·실행 이력
        </div>
        <div className="mb-3 text-[10.5px] text-[var(--text-tertiary)]">발송 {sopHistory.sop_count}건</div>

        {sopHistory.dispatches.length === 0 ? (
          <div className="rounded-md border border-dashed border-[var(--border-dashed)] px-3 py-3 text-[11px] text-[var(--text-secondary)]">
            SOP가 발송되지 않았습니다.
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {sopHistory.dispatches.map((item) => (
              <div key={item.sop_id} className="rounded-md border border-[var(--border)] bg-[var(--panel-bg-2)] p-3">
                <div className="flex items-center justify-between">
                  <div className="text-[12.5px] font-bold text-[var(--text-primary)]">{item.role ?? "담당자 미상"}</div>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                      STATUS_COLOR[item.status] ?? "border-[var(--border-mid)] text-[var(--text-secondary)]"
                    }`}
                  >
                    {item.status}
                  </span>
                </div>
                {item.action_summary && (
                  <div className="mt-1 text-[11px] text-[var(--text-secondary)]">{item.action_summary}</div>
                )}
                <div className="mt-1.5 text-[10.5px] text-[var(--text-tertiary)]">
                  발송 {formatDateTime(item.dispatched_at)} ㆍ 발송자 {item.dispatched_by}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
        <div className="mb-1 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">
          자원 확보 실패·실행 편차와 에스컬레이션 이력
        </div>
        <div className="mb-3 text-[10.5px] text-[var(--text-tertiary)]">
          편차/에스컬레이션 {deviationHistory.deviation_event_count}건
        </div>

        <TimelineView events={deviationHistory.events} />
      </div>
    </div>
  );
}
