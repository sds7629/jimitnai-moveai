import type { AiStatus, ApprovalAction, IncidentDashboardData, RankingMode } from "./types";
import { Header } from "./components/Header";
import { IncidentContextBar } from "./components/IncidentContextBar";
import { ImpactDag } from "./components/ImpactDag";
import { CandidateRankingPanel } from "./components/CandidateRankingPanel";
import { SopPanel } from "./components/SopPanel";
import { ApprovalPanel } from "./components/ApprovalPanel";

export interface IncidentDashboardProps {
  data: IncidentDashboardData;
  /** 라이트/다크 테마. 기본 다크. */
  theme?: "dark" | "light";
  aiStatus?: AiStatus;
  rankingMode?: RankingMode;
  showSopDemoNote?: boolean;
  onRerun?: () => void;
  onApprovalAction?: (action: ApprovalAction) => void;
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
  theme = "dark",
  aiStatus = "cache_fallback",
  rankingMode = "individual",
  showSopDemoNote = true,
  onRerun,
  onApprovalAction,
}: IncidentDashboardProps) {
  return (
    <div
      data-theme={theme}
      className="flex min-h-screen flex-col bg-[var(--bg-page)] text-[var(--text-primary)]"
    >
      <Header aiStatus={aiStatus} />
      <IncidentContextBar incident={data.incident} onRerun={onRerun} />
      <ImpactDag dag={data.dag} />

      <div className="flex gap-4 p-7">
        <CandidateRankingPanel
          candidates={data.candidates}
          excludedCandidates={data.excludedCandidates}
          rankingMode={rankingMode}
        />
        <SopPanel sops={data.sops} matchedCount={data.matchedSopCount} showDemoNote={showSopDemoNote} />
        <ApprovalPanel onAction={onApprovalAction} />
      </div>
    </div>
  );
}
