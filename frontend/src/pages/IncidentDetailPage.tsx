import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { IncidentDashboard } from "../features/incident-dashboard/IncidentDashboard";
import { strikeScenarioMock } from "../features/incident-dashboard/mockData";
import type { DagColumn } from "../features/incident-dashboard/types";
import { listIncidents } from "../features/incidents/api";
import { getImpactDag } from "../features/impact-dag/api";
import { layoutDagIntoColumns } from "../features/impact-dag/layout";
import { getLatestSnapshot } from "../features/snapshot/api";
import { formatQualityMode, summarizeSnapshot, type SnapshotSummary } from "../features/snapshot/format";
import { listCandidates, runSimulation } from "../features/candidates/api";
import { mapCandidatesToDashboard } from "../features/candidates/mapping";
import type { CandidateApi } from "../features/candidates/types";
import { getDecisionPackage } from "../features/decision-package/api";
import type { DecisionPackageApi } from "../features/decision-package/types";
import { submitApproval } from "../features/approvals/api";
import { APPROVAL_ACTION_TO_DECISION_TYPE } from "../features/approvals/types";
import type { ApprovalAction } from "../features/incident-dashboard/types";
import { useIncidentStream } from "../features/stream/useIncidentStream";
import { dispatchSop, getSopStatus } from "../features/sop-dispatch/api";
import type { SopStatusItemApi } from "../features/sop-dispatch/types";
import { getTimeline, updateSopStatus } from "../features/execution-tracking/api";
import type { SopTransitionStatus, TimelineEventApi } from "../features/execution-tracking/types";

/** dispatch-sop을 트리거하는 결정 타입 — communication.py의 APPROVAL_DECISION_TYPES_ELIGIBLE_FOR_DISPATCH
 * ('승인'/'조건부승인')와 일치. 반려/수정요청은 incident.status가 '승인'으로 안 바뀌므로 호출해도
 * 어차피 409지만, 애초에 시도하지 않는다. */
const DISPATCH_ELIGIBLE_ACTIONS: readonly ApprovalAction[] = ["approve", "conditional"];

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "not_found" }
  | {
      status: "success";
      incidentName: string;
      progressBadge: string;
      dagColumns: DagColumn[];
      snapshot: SnapshotSummary;
      candidatesApi: CandidateApi[];
      decisionPackage: DecisionPackageApi | undefined;
      sopStatuses: SopStatusItemApi[];
      timelineEvents: TimelineEventApi[];
    };

/**
 * 사건 상세 화면 (frontend/docs/FEATURE_PHASES.md Phase 2~3~5~6).
 *
 * incident(GET /incidents 목록에서 찾음), impact-dag, 운영 스냅샷을 마운트 시 병렬로 조회해서
 * 실제 데이터로 채운다. SOP/승인 패널은 아직 백엔드 API가 없어서 strikeScenarioMock의 값을 그대로
 * 유지한다 — 해당 API가 생기면 이 부분만 실제 호출로 바뀐다 (Phase 8 이후).
 *
 * 대응안 후보ㆍ의사결정 근거는 **마운트 시점에는 조회하지 않는다.** 사용자가 "실행"/"다시 실행"을
 * 누르기 전까지 DB에 이미 있던(과거 실행분ㆍ시드 데이터) 결과를 화면에 보여주면, 방금 누른 액션의
 * 결과인지 원래 있던 데이터인지 구분할 수 없는 문제가 있었다 — 그래서 candidatesApi는 빈 배열,
 * decisionPackage는 undefined로 시작하고, handleRerun이 성공했을 때만 채워진다. "실행" 버튼 라벨도
 * decisionPackage 유무로 "실행"/"다시 실행"을 오간다(IncidentDashboard→IncidentContextBar로 전달).
 *
 * GET /incidents/{id} 단건 조회 엔드포인트가 없어서, 목록을 통째로 받아 id로 찾는 방식을 쓴다.
 * "실행"/"다시 실행"은 POST /simulate를 트리거한 뒤 candidates·decision-package를 다시 조회한다 —
 * decision-package는 백엔드가 "최신 시뮬레이션 이후면 새로 만들고, 아니면 재사용"하는 캐싱 정책을
 * 쓰므로(app/api/decision_package.py) 재시뮬레이션 후에는 반드시 다시 불러와야 최신 내용이 반영된다.
 * LLM 호출이 섞여있어 몇 초 걸릴 수 있으므로 isRerunning으로 버튼을 잠그고, 실패해도 기존 화면은
 * 그대로 유지한다(최초 실행이 실패하면 candidatesApi/decisionPackage는 계속 비어있는 채로 남는다).
 */
export function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const incidentId = Number(id);
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [isRerunning, setIsRerunning] = useState(false);
  const [rerunError, setRerunError] = useState<string | undefined>(undefined);
  const [isSubmittingApproval, setIsSubmittingApproval] = useState(false);
  const [approvalError, setApprovalError] = useState<string | undefined>(undefined);
  const [deadlineOverrunNotice, setDeadlineOverrunNotice] = useState(false);
  const [isUpdatingSopStatus, setIsUpdatingSopStatus] = useState(false);
  const [sopStatusUpdateError, setSopStatusUpdateError] = useState<string | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      listIncidents(),
      getImpactDag(incidentId),
      getLatestSnapshot(incidentId),
      getSopStatus(incidentId),
      getTimeline(incidentId),
    ])
      .then(([incidents, dag, snapshot, sopStatusResponse, timelineResponse]) => {
        if (cancelled) return;

        const incident = incidents.find((item) => item.id === incidentId);
        if (!incident) {
          setState({ status: "not_found" });
          return;
        }

        const snapshotSummary = summarizeSnapshot(snapshot);
        setState({
          status: "success",
          incidentName: incident.type,
          // quality_mode("normal"/"limited")와 scenario_version(내부 시나리오 슬러그+리비전, 예:
          // "scenario-strike-v1")은 내부 코드일 뿐 사용자에게 그대로 보여줄 문구가 아니다.
          // quality_mode는 한글 라벨로 번역하고, scenario_version 대신 이미 화면에 쓰는
          // snapshot의 최신성 라벨을 붙인다 (내부 슬러그를 한글로 억지로 옮기지 않는다).
          progressBadge: `${formatQualityMode(dag.quality_mode)} ㆍ 최신성 ${snapshotSummary.freshnessLabel}`,
          dagColumns: layoutDagIntoColumns(dag.nodes, dag.edges),
          snapshot: snapshotSummary,
          // 대응안 후보ㆍ의사결정 근거는 "실행" 버튼을 눌러야만 채워진다 — 위 클래스 주석 참고.
          candidatesApi: [],
          decisionPackage: undefined,
          sopStatuses: sopStatusResponse.sop_statuses,
          timelineEvents: timelineResponse.events,
        });
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

  const handleRerun = useCallback(async () => {
    setIsRerunning(true);
    setRerunError(undefined);
    try {
      await runSimulation(incidentId);
      const [{ candidates }, decisionPackage] = await Promise.all([
        listCandidates(incidentId),
        getDecisionPackage(incidentId),
      ]);
      setState((prev) =>
        prev.status === "success" ? { ...prev, candidatesApi: candidates, decisionPackage } : prev,
      );
    } catch (error: unknown) {
      setRerunError(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setIsRerunning(false);
    }
  }, [incidentId]);

  const handleApprovalSubmit = useCallback(
    async (action: ApprovalAction, reason: string, approver: string) => {
      setIsSubmittingApproval(true);
      setApprovalError(undefined);
      try {
        const approval = await submitApproval(incidentId, {
          decision_type: APPROVAL_ACTION_TO_DECISION_TYPE[action],
          reason,
          approver,
        });
        // 수정요청은 서버에서 재시뮬레이션을 트리거하므로, 모든 결정 타입에 대해 동일하게
        // candidates·decision-package를 다시 불러와 최신 상태를 반영한다.
        const [{ candidates }, decisionPackage] = await Promise.all([
          listCandidates(incidentId),
          getDecisionPackage(incidentId),
        ]);
        setState((prev) =>
          prev.status === "success" ? { ...prev, candidatesApi: candidates, decisionPackage } : prev,
        );

        // 승인/조건부승인만 SOP 발송 대상이다(communication.py). 발송 자체가 실패해도 승인은 이미
        // 기록됐으므로 approvalError로는 올리지 않고 조용히 무시한다 — 다음 번 상세 조회/새로고침
        // 시 sop-status를 다시 읽으면 되고, 승인 결과 자체를 되돌릴 이유는 아니다.
        if (DISPATCH_ELIGIBLE_ACTIONS.includes(action)) {
          try {
            await dispatchSop(approval.id);
            const sopStatusResponse = await getSopStatus(incidentId);
            setState((prev) =>
              prev.status === "success" ? { ...prev, sopStatuses: sopStatusResponse.sop_statuses } : prev,
            );
          } catch {
            // 위 주석 참고 — 승인 성공 화면은 그대로 유지한다.
          }
        }
      } catch (error: unknown) {
        setApprovalError(error instanceof Error ? error.message : "알 수 없는 오류");
      } finally {
        setIsSubmittingApproval(false);
      }
    },
    [incidentId],
  );

  const handleSopStatusUpdate = useCallback(
    async (sopId: number, status: SopTransitionStatus, actor: string) => {
      setIsUpdatingSopStatus(true);
      setSopStatusUpdateError(undefined);
      try {
        const transition = await updateSopStatus(sopId, { status, actor });

        const [sopStatusResponse, timelineResponse] = await Promise.all([
          getSopStatus(incidentId),
          getTimeline(incidentId),
        ]);
        setState((prev) =>
          prev.status === "success"
            ? { ...prev, sopStatuses: sopStatusResponse.sop_statuses, timelineEvents: timelineResponse.events }
            : prev,
        );

        // 편차가 감지되면 서버가 오케스트레이션을 거쳐 DAG/후보/의사결정 패키지를 재계산할 수 있다
        // (execution_tracking.py check_and_handle_deviation) — 전체 화면을 최신 상태로 맞춘다.
        if (transition.deviation_check) {
          const [dag, snapshot, { candidates }, decisionPackage] = await Promise.all([
            getImpactDag(incidentId),
            getLatestSnapshot(incidentId),
            listCandidates(incidentId),
            getDecisionPackage(incidentId),
          ]);
          const snapshotSummary = summarizeSnapshot(snapshot);
          setState((prev) =>
            prev.status === "success"
              ? {
                  ...prev,
                  dagColumns: layoutDagIntoColumns(dag.nodes, dag.edges),
                  snapshot: snapshotSummary,
                  progressBadge: `${formatQualityMode(dag.quality_mode)} ㆍ 최신성 ${snapshotSummary.freshnessLabel}`,
                  candidatesApi: candidates,
                  decisionPackage,
                }
              : prev,
          );
        }
      } catch (error: unknown) {
        setSopStatusUpdateError(error instanceof Error ? error.message : "알 수 없는 오류");
      } finally {
        setIsUpdatingSopStatus(false);
      }
    },
    [incidentId],
  );

  // GET /incidents/{id}/stream (SSE) — 서버가 2~3초 간격으로 dag_updated/decision_package_updated/
  // deadline_overrun을 push한다. TanStack Query 없이 지금 구조 그대로, 해당 리소스만 다시 fetch한다.
  const refetchDagAndSnapshot = useCallback(async () => {
    const [dag, snapshot] = await Promise.all([getImpactDag(incidentId), getLatestSnapshot(incidentId)]);
    const snapshotSummary = summarizeSnapshot(snapshot);
    setState((prev) =>
      prev.status === "success"
        ? {
            ...prev,
            dagColumns: layoutDagIntoColumns(dag.nodes, dag.edges),
            snapshot: snapshotSummary,
            progressBadge: `${formatQualityMode(dag.quality_mode)} ㆍ 최신성 ${snapshotSummary.freshnessLabel}`,
          }
        : prev,
    );
  }, [incidentId]);

  const refetchDecisionPackage = useCallback(async () => {
    const decisionPackage = await getDecisionPackage(incidentId);
    setState((prev) => (prev.status === "success" ? { ...prev, decisionPackage } : prev));
  }, [incidentId]);

  useIncidentStream(incidentId, {
    onDagUpdated: () => void refetchDagAndSnapshot(),
    onDecisionPackageUpdated: () => void refetchDecisionPackage(),
    onDeadlineOverrun: () => setDeadlineOverrunNotice(true),
  });

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
        사건 정보를 불러오지 못했습니다: {state.message}
      </div>
    );
  }

  if (state.status === "not_found") {
    return (
      <div data-theme="dark" className="min-h-screen bg-[var(--bg-page)] p-7 text-[var(--text-secondary)]">
        사건을 찾을 수 없습니다.
      </div>
    );
  }

  const { candidates, excludedCandidates } = mapCandidatesToDashboard(state.candidatesApi);

  return (
    <IncidentDashboard
      data={{
        ...strikeScenarioMock,
        incident: {
          name: state.incidentName,
          progressBadge: state.progressBadge,
          rawTextPlaceholder: strikeScenarioMock.incident.rawTextPlaceholder,
        },
        dag: state.dagColumns,
        candidates,
        excludedCandidates,
      }}
      snapshot={state.snapshot}
      decisionPackage={state.decisionPackage}
      isRerunning={isRerunning}
      rerunError={rerunError}
      onRerun={handleRerun}
      isSubmittingApproval={isSubmittingApproval}
      approvalError={approvalError}
      onApprovalSubmit={handleApprovalSubmit}
      deadlineOverrunNotice={deadlineOverrunNotice}
      sopStatuses={state.sopStatuses}
      isUpdatingSopStatus={isUpdatingSopStatus}
      sopStatusUpdateError={sopStatusUpdateError}
      onSopStatusUpdate={handleSopStatusUpdate}
      timelineEvents={state.timelineEvents}
      postReportHref={`/incidents/${incidentId}/post-report`}
    />
  );
}
