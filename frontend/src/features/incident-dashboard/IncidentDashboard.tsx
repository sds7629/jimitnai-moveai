import type { AiStatus, ApprovalAction, IncidentDashboardData } from "./types";
import { useTheme } from "../../lib/useTheme";
import type { SnapshotSummary } from "../snapshot/format";
import type { DecisionPackageApi } from "../decision-package/types";
import type { SopStatusItemApi } from "../sop-dispatch/types";
import type { SopTransitionStatus, TimelineEventApi } from "../execution-tracking/types";
import { Header } from "./components/Header";
import { IncidentContextBar } from "./components/IncidentContextBar";
import { SnapshotStatusBar } from "./components/SnapshotStatusBar";
import { ImpactDag } from "./components/ImpactDag";
import { DecisionPackagePanel } from "./components/DecisionPackagePanel";
import { CandidateRankingPanel } from "./components/CandidateRankingPanel";
import { SopPanel } from "./components/SopPanel";
import { SopDispatchPanel } from "./components/SopDispatchPanel";
import { TimelineView } from "./components/TimelineView";
import { ApprovalPanel } from "./components/ApprovalPanel";

export interface IncidentDashboardProps {
  data: IncidentDashboardData;
  /** 라이트/다크 테마 초기값 — localStorage에 저장된 선택이 이미 있으면 그게 우선이고, 없을 때만
   * 이 값이 초기값으로 쓰인다. 헤더 우상단 토글 버튼으로 전환하면 앱 전역에서 공유하는
   * localStorage 값(useTheme, frontend/src/lib/useTheme.ts)에 반영되어 다른 페이지에도 유지된다. */
  theme?: "dark" | "light";
  aiStatus?: AiStatus;
  showSopDemoNote?: boolean;
  /** 없으면 스냅샷 상태 바를 렌더링하지 않는다 (Phase 3 이전 호출부와의 호환) */
  snapshot?: SnapshotSummary;
  /** 없으면 의사결정 근거 패널을 렌더링하지 않는다 (Phase 6 이전 호출부와의 호환) */
  decisionPackage?: DecisionPackageApi;
  /** POST /simulate가 진행 중일 때 "실행"/"다시 실행" 버튼에 로딩 상태를 표시 (Phase 5) */
  isRerunning?: boolean;
  rerunError?: string;
  /** POST /approvals가 진행 중일 때 승인 액션 버튼들을 잠근다 (Phase 7) */
  isSubmittingApproval?: boolean;
  approvalError?: string;
  /** SSE deadline_overrun 이벤트 수신 시 true — 결정기한 초과 경고 배너 표시 (Phase 8) */
  deadlineOverrunNotice?: boolean;
  /** undefined면 패널 자체를 렌더링하지 않는다(Phase 9 이전 호출부와의 호환). 빈 배열이면 패널은
   * 보이되 "아직 발송되지 않음" 안내를 보여준다 — 승인 전에는 실제로 발송 이력이 없는 게 정상이다. */
  sopStatuses?: SopStatusItemApi[];
  /** PATCH /sop/{sop_id}/status가 진행 중일 때 상태 전이 버튼들을 잠근다 (Phase 10) */
  isUpdatingSopStatus?: boolean;
  sopStatusUpdateError?: string;
  /** undefined면 타임라인 섹션을 렌더링하지 않는다 (Phase 10) */
  timelineEvents?: TimelineEventApi[];
  /** 없으면 "사후보고서 보기" 링크를 렌더링하지 않는다 (Phase 11) */
  postReportHref?: string;
  onRerun?: () => void;
  onApprovalSubmit?: (action: ApprovalAction, reason: string, approver: string) => void;
  onSopStatusUpdate?: (sopId: number, status: SopTransitionStatus, actor: string) => void;
}

/**
 * 인시던트 대응 통합 대시보드 (DAG + 대응안 랭킹 + SOP 자동 안내 + 승인 액션).
 *
 * Claude 디자인 와이어프레임(DAG 대시보드.dc.html)을 실제 React 컴포넌트로 옮긴 것.
 * frontend/DAG_SCREEN_DESIGN_BRIEF.md §0에서 미정이었던 "탭 분리 vs 단일 대시보드" 구조 이슈는
 * 이 와이어프레임 자체가 단일 대시보드로 확정해서 넘어온 것으로 보고 그대로 반영했다.
 * FRONTEND_ARCHITECTURE.md §3의 개별 라우트(dag/candidates/sop/approval)는 이 화면의
 * 드릴다운 상세 화면으로 재배치할지 추후 논의 필요.
 */
export function IncidentDashboard({
  data,
  theme: initialTheme = "dark",
  aiStatus = "cache_fallback",
  showSopDemoNote = true,
  snapshot,
  decisionPackage,
  isRerunning = false,
  rerunError,
  isSubmittingApproval = false,
  approvalError,
  deadlineOverrunNotice = false,
  sopStatuses,
  isUpdatingSopStatus = false,
  sopStatusUpdateError,
  timelineEvents,
  postReportHref,
  onRerun,
  onApprovalSubmit,
  onSopStatusUpdate,
}: IncidentDashboardProps) {
  // theme prop은 localStorage에 아직 저장된 선택이 없을 때만 쓰이는 초기값이고, 이후 전환은
  // 앱 전역에서 공유하는 useTheme 훅(localStorage 백업)이 관리한다 — 헤더에서 전환하면 다른
  // 페이지(사후보고서 등)에서도 같은 선택이 유지된다.
  const { theme, toggleTheme } = useTheme(initialTheme);

  return (
    <div
      data-theme={theme}
      className="flex min-h-screen flex-col bg-[var(--bg-page)] text-[var(--text-primary)]"
    >
      <Header aiStatus={aiStatus} theme={theme} onToggleTheme={toggleTheme} />
      {deadlineOverrunNotice && (
        <div className="border-b border-[var(--red-border)] bg-[var(--red-chip-bg)] px-7 py-2 text-[11.5px] font-semibold text-[var(--red)]">
          ⚠ 결정기한이 초과되어 상위 책임자에게 에스컬레이션이 기록되었습니다.
        </div>
      )}
      <IncidentContextBar
        incident={data.incident}
        onRerun={onRerun}
        isRerunning={isRerunning}
        hasResults={decisionPackage !== undefined}
        rerunError={rerunError}
        postReportHref={postReportHref}
      />
      {snapshot && <SnapshotStatusBar snapshot={snapshot} />}
      <ImpactDag dag={data.dag} />

      {decisionPackage && (
        <div className="px-7 pt-5">
          <DecisionPackagePanel decisionPackage={decisionPackage} />
        </div>
      )}

      <div className="flex gap-4 p-7">
        <CandidateRankingPanel candidates={data.candidates} excludedCandidates={data.excludedCandidates} />
        <SopPanel sops={data.sops} matchedCount={data.matchedSopCount} showDemoNote={showSopDemoNote} />
        <ApprovalPanel
          isSubmitting={isSubmittingApproval}
          submitError={approvalError}
          onSubmit={onApprovalSubmit}
        />
      </div>

      {sopStatuses !== undefined && (
        <div className="px-7 pb-7">
          <SopDispatchPanel
            sopStatuses={sopStatuses}
            isUpdating={isUpdatingSopStatus}
            updateError={sopStatusUpdateError}
            onStatusUpdate={onSopStatusUpdate}
          />
        </div>
      )}

      {timelineEvents !== undefined && (
        <div className="px-7 pb-7">
          <div className="rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
            <div className="mb-3 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">실행 추적 타임라인</div>
            <TimelineView events={timelineEvents} />
          </div>
        </div>
      )}
    </div>
  );
}
