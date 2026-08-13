import { useState } from "react";
import type { AiStatus, ApprovalAction, IncidentDashboardData } from "./types";
import type { SnapshotSummary } from "../snapshot/format";
import type { DecisionPackageApi } from "../decision-package/types";
import { Header } from "./components/Header";
import { IncidentContextBar } from "./components/IncidentContextBar";
import { SnapshotStatusBar } from "./components/SnapshotStatusBar";
import { ImpactDag } from "./components/ImpactDag";
import { DecisionPackagePanel } from "./components/DecisionPackagePanel";
import { CandidateRankingPanel } from "./components/CandidateRankingPanel";
import { SopPanel } from "./components/SopPanel";
import { ApprovalPanel } from "./components/ApprovalPanel";

export interface IncidentDashboardProps {
  data: IncidentDashboardData;
  /** 라이트/다크 테마 초기값. 기본 다크. 헤더 우상단 토글 버튼으로 이후 전환 가능(내부 상태로 관리). */
  theme?: "dark" | "light";
  aiStatus?: AiStatus;
  showSopDemoNote?: boolean;
  /** 없으면 스냅샷 상태 바를 렌더링하지 않는다 (Phase 3 이전 호출부와의 호환) */
  snapshot?: SnapshotSummary;
  /** 없으면 의사결정 근거 패널을 렌더링하지 않는다 (Phase 6 이전 호출부와의 호환) */
  decisionPackage?: DecisionPackageApi;
  /** POST /simulate가 진행 중일 때 "다시 실행" 버튼에 로딩 상태를 표시 (Phase 5) */
  isRerunning?: boolean;
  rerunError?: string;
  /** POST /approvals가 진행 중일 때 승인 액션 버튼들을 잠근다 (Phase 7) */
  isSubmittingApproval?: boolean;
  approvalError?: string;
  onRerun?: () => void;
  onApprovalSubmit?: (action: ApprovalAction, reason: string, approver: string) => void;
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
  onRerun,
  onApprovalSubmit,
}: IncidentDashboardProps) {
  // theme prop은 초기값으로만 쓰고, 이후 전환은 헤더의 토글 버튼으로 내부 상태에서 관리한다
  const [theme, setTheme] = useState<"dark" | "light">(initialTheme);
  const toggleTheme = () => setTheme((current) => (current === "dark" ? "light" : "dark"));

  return (
    <div
      data-theme={theme}
      className="flex min-h-screen flex-col bg-[var(--bg-page)] text-[var(--text-primary)]"
    >
      <Header aiStatus={aiStatus} theme={theme} onToggleTheme={toggleTheme} />
      <IncidentContextBar
        incident={data.incident}
        onRerun={onRerun}
        isRerunning={isRerunning}
        rerunError={rerunError}
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
    </div>
  );
}
