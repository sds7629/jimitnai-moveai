import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listIncidents } from "../features/incidents/api";
import type { IncidentListItem } from "../features/incidents/types";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; incidents: IncidentListItem[] };

/**
 * 진입 화면: 시드 시나리오(적체/파업/관세) 목록.
 * frontend/docs/FEATURE_PHASES.md Phase 1 — 별도 사건 생성 폼 없이 GET /incidents로
 * DB에 이미 시드된 3개 사건을 바로 불러온다.
 */
export function IncidentListPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    listIncidents()
      .then((incidents) => {
        if (!cancelled) setState({ status: "success", incidents });
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
  }, []);

  return (
    <div
      data-theme="dark"
      className="min-h-screen bg-[var(--bg-page)] px-7 py-6 text-[var(--text-primary)]"
    >
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-[19px] font-bold">사건 목록</h1>
        <Link
          to="/reports/roi"
          className="rounded-md border border-[var(--border-btn)] px-3.5 py-2 text-[12.5px] font-bold text-[var(--text-body)]"
        >
          연간 ROI 보기
        </Link>
      </div>

      {state.status === "loading" && (
        <div className="text-[13px] text-[var(--text-secondary)]">불러오는 중...</div>
      )}

      {state.status === "error" && (
        <div className="text-[13px] text-[var(--red)]">
          사건 목록을 불러오지 못했습니다: {state.message}
        </div>
      )}

      {state.status === "success" && state.incidents.length === 0 && (
        <div className="text-[13px] text-[var(--text-secondary)]">표시할 사건이 없습니다.</div>
      )}

      {state.status === "success" && state.incidents.length > 0 && (
        <ul className="flex flex-col gap-3">
          {state.incidents.map((incident) => (
            <li key={incident.id}>
              <Link
                to={`/incidents/${incident.id}`}
                className="block rounded-md border border-[var(--border)] bg-[var(--panel-bg)] p-4 hover:border-[var(--blue)]"
              >
                <div className="text-[14px] font-bold text-[var(--text-primary)]">{incident.type}</div>
                <div className="mt-1 text-[11.5px] text-[var(--text-secondary)]">
                  {incident.location} ㆍ {incident.status}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
