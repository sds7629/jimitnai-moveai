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
    };

/**
 * 사건 상세 화면 (frontend/docs/FEATURE_PHASES.md Phase 2~3~5).
 *
 * incident(GET /incidents 목록에서 찾음), impact-dag, 운영 스냅샷, 대응안 후보를 병렬로 조회해서
 * 실제 데이터로 채운다. SOP/승인 패널은 아직 백엔드 API가 없어서 strikeScenarioMock의 값을 그대로
 * 유지한다 — 해당 API가 생기면 이 부분만 실제 호출로 바뀐다 (Phase 8 이후).
 *
 * GET /incidents/{id} 단건 조회 엔드포인트가 없어서, 목록을 통째로 받아 id로 찾는 방식을 쓴다.
 * "다시 실행"은 POST /simulate를 트리거한 뒤 GET /candidates를 다시 조회한다 — LLM 호출이 섞여있어
 * 몇 초 걸릴 수 있으므로 isRerunning으로 버튼을 잠그고, 실패해도 기존 화면은 그대로 유지한다.
 */
export function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const incidentId = Number(id);
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [isRerunning, setIsRerunning] = useState(false);
  const [rerunError, setRerunError] = useState<string | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      listIncidents(),
      getImpactDag(incidentId),
      getLatestSnapshot(incidentId),
      listCandidates(incidentId),
    ])
      .then(([incidents, dag, snapshot, candidatesResponse]) => {
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
      const { candidates } = await listCandidates(incidentId);
      setState((prev) => (prev.status === "success" ? { ...prev, candidatesApi: candidates } : prev));
    } catch (error: unknown) {
      setRerunError(error instanceof Error ? error.message : "알 수 없는 오류");
    } finally {
      setIsRerunning(false);
    }
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
      isRerunning={isRerunning}
      rerunError={rerunError}
      onRerun={handleRerun}
    />
  );
}
