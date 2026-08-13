import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { IncidentDashboard } from "../features/incident-dashboard/IncidentDashboard";
import { strikeScenarioMock } from "../features/incident-dashboard/mockData";
import type { DagColumn } from "../features/incident-dashboard/types";
import { listIncidents } from "../features/incidents/api";
import { getImpactDag } from "../features/impact-dag/api";
import { layoutDagIntoColumns } from "../features/impact-dag/layout";
import { getLatestSnapshot } from "../features/snapshot/api";
import { summarizeSnapshot, type SnapshotSummary } from "../features/snapshot/format";
import { listCandidates, runSimulation } from "../features/candidates/api";
import { mapCandidatesToDashboard } from "../features/candidates/mapping";
import type { CandidateApi } from "../features/candidates/types";
import { getDecisionPackage } from "../features/decision-package/api";
import type { DecisionPackageApi } from "../features/decision-package/types";
import { submitApproval } from "../features/approvals/api";
import { APPROVAL_ACTION_TO_DECISION_TYPE } from "../features/approvals/types";
import type { ApprovalAction } from "../features/incident-dashboard/types";

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
      decisionPackage: DecisionPackageApi;
    };

/**
 * 사건 상세 화면 (frontend/docs/FEATURE_PHASES.md Phase 2~3~5~6).
 *
 * incident(GET /incidents 목록에서 찾음), impact-dag, 운영 스냅샷, 대응안 후보, 의사결정 근거를
 * 병렬로 조회해서 실제 데이터로 채운다. SOP/승인 패널은 아직 백엔드 API가 없어서
 * strikeScenarioMock의 값을 그대로 유지한다 — 해당 API가 생기면 이 부분만 실제 호출로 바뀐다
 * (Phase 8 이후).
 *
 * GET /incidents/{id} 단건 조회 엔드포인트가 없어서, 목록을 통째로 받아 id로 찾는 방식을 쓴다.
 * "다시 실행"은 POST /simulate를 트리거한 뒤 candidates·decision-package를 다시 조회한다 —
 * decision-package는 백엔드가 "최신 시뮬레이션 이후면 새로 만들고, 아니면 재사용"하는 캐싱 정책을
 * 쓰므로(app/api/decision_package.py) 재시뮬레이션 후에는 반드시 다시 불러와야 최신 내용이 반영된다.
 * LLM 호출이 섞여있어 몇 초 걸릴 수 있으므로 isRerunning으로 버튼을 잠그고, 실패해도 기존 화면은
 * 그대로 유지한다.
 */
export function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const incidentId = Number(id);
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [isRerunning, setIsRerunning] = useState(false);
  const [rerunError, setRerunError] = useState<string | undefined>(undefined);
  const [isSubmittingApproval, setIsSubmittingApproval] = useState(false);
  const [approvalError, setApprovalError] = useState<string | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      listIncidents(),
      getImpactDag(incidentId),
      getLatestSnapshot(incidentId),
      listCandidates(incidentId),
      getDecisionPackage(incidentId),
    ])
      .then(([incidents, dag, snapshot, candidatesResponse, decisionPackage]) => {
        if (cancelled) return;

        const incident = incidents.find((item) => item.id === incidentId);
        if (!incident) {
          setState({ status: "not_found" });
          return;
        }

        setState({
          status: "success",
          incidentName: incident.type,
          progressBadge: `${dag.quality_mode} ㆍ ${dag.scenario_version}`,
          dagColumns: layoutDagIntoColumns(dag.nodes, dag.edges),
          snapshot: summarizeSnapshot(snapshot),
          candidatesApi: candidatesResponse.candidates,
          decisionPackage,
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
        await submitApproval(incidentId, {
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
      } catch (error: unknown) {
        setApprovalError(error instanceof Error ? error.message : "알 수 없는 오류");
      } finally {
        setIsSubmittingApproval(false);
      }
    },
    [incidentId],
  );

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
    />
  );
}
