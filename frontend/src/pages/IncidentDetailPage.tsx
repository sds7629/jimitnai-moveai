import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { IncidentDashboard } from "../features/incident-dashboard/IncidentDashboard";
import { strikeScenarioMock } from "../features/incident-dashboard/mockData";
import type { IncidentDashboardData } from "../features/incident-dashboard/types";
import { listIncidents } from "../features/incidents/api";
import { getImpactDag } from "../features/impact-dag/api";
import { layoutDagIntoColumns } from "../features/impact-dag/layout";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "not_found" }
  | { status: "success"; data: IncidentDashboardData };

/**
 * 사건 상세 화면 (frontend/docs/FEATURE_PHASES.md Phase 2).
 *
 * incident(GET /incidents 목록에서 찾음)와 impact-dag(GET /incidents/{id}/impact-dag)를 병렬로
 * 조회해서 실제 데이터로 채운다. 대응안 랭킹/SOP/승인 패널은 아직 백엔드 API가 없어서
 * strikeScenarioMock의 값을 그대로 유지한다 — 해당 API가 생기면 이 부분만 실제 호출로 바뀐다
 * (Phase 5 이후).
 *
 * GET /incidents/{id} 단건 조회 엔드포인트가 없어서, 목록을 통째로 받아 id로 찾는 방식을 쓴다.
 */
export function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    const incidentId = Number(id);

    Promise.all([listIncidents(), getImpactDag(incidentId)])
      .then(([incidents, dag]) => {
        if (cancelled) return;

        const incident = incidents.find((item) => item.id === incidentId);
        if (!incident) {
          setState({ status: "not_found" });
          return;
        }

        const data: IncidentDashboardData = {
          ...strikeScenarioMock,
          incident: {
            name: incident.type,
            progressBadge: `${dag.quality_mode} ㆍ ${dag.scenario_version}`,
            rawTextPlaceholder: strikeScenarioMock.incident.rawTextPlaceholder,
          },
          dag: layoutDagIntoColumns(dag.nodes, dag.edges),
        };
        setState({ status: "success", data });
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
  }, [id]);

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

  return <IncidentDashboard data={state.data} />;
}
