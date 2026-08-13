import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getCostAttribution, getPostReport } from "../features/post-report/api";
import {
  COST_ATTRIBUTION_LABELS,
  POST_REPORT_SECTIONS,
  type CandidatesReviewedSection,
  type CostAttributionApi,
  type DynamicVariableChangesSection,
  type ExpectedVsActualProgressSection,
  type FinalDecisionSection,
  type FutureImprovementsSection,
  type OverviewSection,
  type PostReportApi,
  type SimulationErrorSection,
} from "../features/post-report/types";
import { formatKrwToEokwon } from "../lib/currency";
import { OverviewAndDecisionCard } from "../features/post-report/components/OverviewAndDecisionCard";
import { ReviewedCandidatesTable } from "../features/post-report/components/ReviewedCandidatesTable";
import { ExpectedProgressAndChanges } from "../features/post-report/components/ExpectedProgressAndChanges";
import { SimulationErrorAndImprovements } from "../features/post-report/components/SimulationErrorAndImprovements";

/** Phase 19~24에서 전용 UI로 옮긴 섹션 — 아래 일반 JSON 렌더링 목록에서는 제외한다.
 * 앞으로 남은 섹션을 하나씩 옮길 때마다 이 목록에 키를 추가한다
 * (DecisionPackagePanel의 MIGRATED_SECTION_KEYS와 같은 패턴, frontend/docs/FEATURE_PHASES.md Phase 19~24). */
const MIGRATED_SECTION_KEYS = new Set([
  "1_사건_개요와_발생시점",
  "2_최초_예상과_실제_진행_과정",
  "3_주요_동적_변수의_변화",
  "4_검토한_대응안과_제외_사유",
  "5_최종_결정과_승인자",
  "10_시뮬레이션_오차와_가정의_영향",
  "12_향후_SOP_모델_데이터_개선사항",
]);

const EMPTY_OVERVIEW: OverviewSection = {
  incident_id: 0,
  type: "-",
  location: "-",
  occurred_at: "",
  status: "-",
  duplicate_of_incident_id: null,
  affected_targets: {},
  assumptions_at_intake: [],
  created_at: "",
};
const EMPTY_FINAL_DECISION: FinalDecisionSection = {
  approvals_history: [],
  final_decision: { available: false, reason: "-" },
};
const EMPTY_CANDIDATES_REVIEWED: CandidatesReviewedSection = {
  total_count: 0,
  excluded_count: 0,
  candidates: [],
};
const EMPTY_PROGRESS: ExpectedVsActualProgressSection = {
  expected: { baseline: { available: false }, approved_candidate: { available: false } },
  actual_status: "미확정",
  actual_progress: { available: false, reason: "-" },
};
const EMPTY_CHANGES: DynamicVariableChangesSection = {
  snapshot_count: 0,
  versions: [],
  changes_summary: [],
};
const EMPTY_SIMULATION_ERROR: SimulationErrorSection = {
  error_calculable: false,
  reason: "-",
  candidates: [],
};

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; postReport: PostReportApi; costAttribution: CostAttributionApi };

/**
 * 사후보고서 화면 (frontend/docs/FEATURE_PHASES.md Phase 11).
 *
 * 진행 중 대시보드(/incidents/:id)와 관심사가 달라(사후 정산) 별도 라우트로 분리했다
 * (FRONTEND_ARCHITECTURE.md §3 원래 라우팅 표에도 별도 경로로 계획돼 있었음).
 *
 * report_status는 이 시스템 스코프상 항상 "잠정", actual_status는 항상 "미확정"이다 —
 * scope_limitation_note를 화면 상단에서 숨기지 않고 그대로 보여준다. 비용 귀속도
 * is_heuristic=true인 안전한 휴리스틱이라 heuristic_disclaimer를 함께 노출한다.
 */
export function PostReportPage() {
  const { id } = useParams<{ id: string }>();
  const incidentId = Number(id);
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    Promise.all([getPostReport(incidentId), getCostAttribution(incidentId)])
      .then(([postReport, costAttribution]) => {
        if (!cancelled) setState({ status: "success", postReport, costAttribution });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            status: "error",
            message: error instanceof Error ? error.message : "알 수 없는 오류",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [incidentId]);

  if (state.status === "loading") {
    return (
      <div data-theme="dark" className="min-h-screen bg-[var(--bg-page)] p-7 text-[var(--text-secondary)]">
        불러오는 중...
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div data-theme="dark" className="min-h-screen bg-[var(--bg-page)] p-7 text-[var(--red)]">
        사후보고서를 불러오지 못했습니다: {state.message}
      </div>
    );
  }

  const { postReport, costAttribution } = state;
  // 백엔드 blob이 loosely-typed dict라 섹션 키 자체는 있어도 하위 필드가 빠질 수 있다
  // (frontend/docs/FEATURE_PHASES.md Phase 14 undefined 버그와 같은 패턴) — 필드별 기본값 처리한다.
  const rawOverview = (postReport.sections["1_사건_개요와_발생시점"] ?? {}) as Partial<OverviewSection>;
  const overview: OverviewSection = {
    incident_id: rawOverview.incident_id ?? EMPTY_OVERVIEW.incident_id,
    type: rawOverview.type ?? EMPTY_OVERVIEW.type,
    location: rawOverview.location ?? EMPTY_OVERVIEW.location,
    occurred_at: rawOverview.occurred_at ?? EMPTY_OVERVIEW.occurred_at,
    status: rawOverview.status ?? EMPTY_OVERVIEW.status,
    duplicate_of_incident_id: rawOverview.duplicate_of_incident_id ?? EMPTY_OVERVIEW.duplicate_of_incident_id,
    affected_targets: rawOverview.affected_targets ?? EMPTY_OVERVIEW.affected_targets,
    assumptions_at_intake: rawOverview.assumptions_at_intake ?? EMPTY_OVERVIEW.assumptions_at_intake,
    created_at: rawOverview.created_at ?? EMPTY_OVERVIEW.created_at,
  };
  const rawProgress = (postReport.sections["2_최초_예상과_실제_진행_과정"] ??
    {}) as Partial<ExpectedVsActualProgressSection>;
  const progress: ExpectedVsActualProgressSection = {
    expected: rawProgress.expected ?? EMPTY_PROGRESS.expected,
    actual_status: rawProgress.actual_status ?? EMPTY_PROGRESS.actual_status,
    actual_progress: rawProgress.actual_progress ?? EMPTY_PROGRESS.actual_progress,
  };
  const rawChanges = (postReport.sections["3_주요_동적_변수의_변화"] ?? {}) as Partial<DynamicVariableChangesSection>;
  const changes: DynamicVariableChangesSection = {
    snapshot_count: rawChanges.snapshot_count ?? EMPTY_CHANGES.snapshot_count,
    versions: rawChanges.versions ?? EMPTY_CHANGES.versions,
    changes_summary: rawChanges.changes_summary ?? EMPTY_CHANGES.changes_summary,
  };
  const rawDecision = (postReport.sections["5_최종_결정과_승인자"] ?? {}) as Partial<FinalDecisionSection>;
  const decision: FinalDecisionSection = {
    approvals_history: rawDecision.approvals_history ?? EMPTY_FINAL_DECISION.approvals_history,
    final_decision: rawDecision.final_decision ?? EMPTY_FINAL_DECISION.final_decision,
  };
  const rawReviewed = (postReport.sections["4_검토한_대응안과_제외_사유"] ?? {}) as Partial<CandidatesReviewedSection>;
  const candidatesReviewed: CandidatesReviewedSection = {
    total_count: rawReviewed.total_count ?? EMPTY_CANDIDATES_REVIEWED.total_count,
    excluded_count: rawReviewed.excluded_count ?? EMPTY_CANDIDATES_REVIEWED.excluded_count,
    candidates: rawReviewed.candidates ?? EMPTY_CANDIDATES_REVIEWED.candidates,
  };
  const rawSimulationError = (postReport.sections["10_시뮬레이션_오차와_가정의_영향"] ??
    {}) as Partial<SimulationErrorSection>;
  const simulationError: SimulationErrorSection = {
    error_calculable: rawSimulationError.error_calculable ?? EMPTY_SIMULATION_ERROR.error_calculable,
    reason: rawSimulationError.reason ?? EMPTY_SIMULATION_ERROR.reason,
    candidates: rawSimulationError.candidates ?? EMPTY_SIMULATION_ERROR.candidates,
  };
  // 섹션 12는 다른 섹션들과 달리 object가 아니라 배열 자체다(_section_12_future_improvements가
  // list[dict]를 직접 반환) — Partial<T> + 필드별 기본값 패턴이 아니라 배열째로 기본값 처리한다.
  const improvements = (postReport.sections["12_향후_SOP_모델_데이터_개선사항"] ?? []) as FutureImprovementsSection;

  return (
    <div data-theme="dark" className="min-h-screen bg-[var(--bg-page)] p-7 text-[var(--text-primary)]">
      <div className="mb-5 flex items-center gap-3">
        <div className="text-[19px] font-bold">사후보고서</div>
        <span className="rounded-full border border-[var(--amber)] px-2.5 py-1 text-[11px] font-semibold text-[var(--amber)]">
          {postReport.report_status}
        </span>
        <span className="rounded-full border border-[var(--border-mid)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
          실적: {postReport.actual_status}
        </span>
      </div>

      <div className="mb-5 rounded-md border border-dashed border-[var(--border-dashed)] bg-[var(--panel-bg-2)] px-3 py-2.5 text-[11px] text-[var(--text-secondary)]">
        {postReport.scope_limitation_note}
      </div>

      <div className="mb-5 rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
        <div className="mb-3 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">
          비용 귀속 {costAttribution.is_heuristic && "(휴리스틱)"}
        </div>
        <div className="mb-2 text-[10.5px] text-[var(--amber)]">{costAttribution.heuristic_disclaimer}</div>
        <div className="flex gap-4">
          {COST_ATTRIBUTION_LABELS.map(({ key, label }) => (
            <div key={key} className="flex-1 rounded-md border border-[var(--border)] p-3">
              <div className="text-[10.5px] text-[var(--text-tertiary)]">{label}</div>
              <div className="mt-1 text-[15px] font-bold text-[var(--teal)]">
                {formatKrwToEokwon(costAttribution.breakdown[key] ?? null)}
              </div>
            </div>
          ))}
        </div>
        {costAttribution.classification_note && (
          <div className="mt-2 text-[10.5px] text-[var(--text-tertiary)]">{costAttribution.classification_note}</div>
        )}
      </div>

      <div className="mb-5">
        <OverviewAndDecisionCard overview={overview} decision={decision} />
      </div>

      <div className="mb-5">
        <ExpectedProgressAndChanges progress={progress} changes={changes} />
      </div>

      <div className="mb-5">
        <ReviewedCandidatesTable section={candidatesReviewed} />
      </div>

      <div className="mb-5">
        <SimulationErrorAndImprovements simulationError={simulationError} improvements={improvements} />
      </div>

      <div className="rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
        {POST_REPORT_SECTIONS.filter(({ key }) => !MIGRATED_SECTION_KEYS.has(key)).map(({ key, label }) => (
          <div key={key} className="border-b border-[var(--border)] py-2.5 last:border-b-0">
            <div className="mb-1 text-[11.5px] font-bold text-[var(--text-secondary-strong)]">{label}</div>
            <pre className="whitespace-pre-wrap break-words rounded bg-[var(--panel-bg-2)] p-2 text-[10px] leading-relaxed text-[var(--text-secondary)]">
              {JSON.stringify(postReport.sections[key] ?? null, null, 2)}
            </pre>
          </div>
        ))}
      </div>
    </div>
  );
}
