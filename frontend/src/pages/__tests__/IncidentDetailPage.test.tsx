import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { IncidentDetailPage } from "../IncidentDetailPage";
import { listIncidents } from "../../features/incidents/api";
import { getImpactDag } from "../../features/impact-dag/api";
import type { IncidentListItem } from "../../features/incidents/types";
import type { ImpactDagApiResponse } from "../../features/impact-dag/types";

vi.mock("../../features/incidents/api");
vi.mock("../../features/impact-dag/api");
const mockListIncidents = vi.mocked(listIncidents);
const mockGetImpactDag = vi.mocked(getImpactDag);

const incidents: IncidentListItem[] = [
  {
    id: 2,
    type: "항만 파업",
    location: "부산항",
    occurred_at: "2026-08-13T02:00:00Z",
    status: "유효",
    duplicate_of_incident_id: null,
    created_at: "2026-08-13T02:00:00Z",
  },
];

const dag: ImpactDagApiResponse = {
  incident_id: 2,
  snapshot_id: 10,
  data_version: "v1",
  scenario_version: "strike-v1",
  quality_mode: "normal",
  nodes: [
    {
      id: 1,
      snapshot_id: 10,
      node_key: "trigger",
      label: "항만/운송 노동 파업",
      affected_target: "부산항 전체",
      expected_time: null,
      basis: "노조 파업 공지",
      responsible_party: "항만운영팀",
      uncertainty: "low",
      created_at: "2026-08-13T02:00:00Z",
    },
  ],
  edges: [],
};

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/incidents/${id}`]}>
      <Routes>
        <Route path="/incidents/:id" element={<IncidentDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("IncidentDetailPage — 정상 시나리오(happy path)", () => {
  it("사건 정보와 실제 DAG를 함께 불러와 대시보드를 렌더링한다", async () => {
    mockListIncidents.mockResolvedValue(incidents);
    mockGetImpactDag.mockResolvedValue(dag);

    renderAt("2");

    expect(await screen.findByText("항만 파업")).toBeInTheDocument();
    expect(screen.getByText("항만/운송 노동 파업")).toBeInTheDocument();
  });
});

describe("IncidentDetailPage — 로딩 상태", () => {
  it("응답이 오기 전에는 로딩 문구를 표시한다", () => {
    mockListIncidents.mockReturnValue(new Promise(() => {}));
    mockGetImpactDag.mockReturnValue(new Promise(() => {}));

    renderAt("2");

    expect(screen.getByText(/불러오는 중/)).toBeInTheDocument();
  });
});

describe("IncidentDetailPage — 예외 케이스", () => {
  it("DAG 조회가 실패하면 에러 메시지를 표시한다", async () => {
    mockListIncidents.mockResolvedValue(incidents);
    mockGetImpactDag.mockRejectedValue(new Error("DAG 조회 실패"));

    renderAt("2");

    expect(await screen.findByText(/불러오지 못했습니다/)).toBeInTheDocument();
  });
});

describe("IncidentDetailPage — 경계값(존재하지 않는 사건)", () => {
  it("목록에 없는 id로 접근하면 사건을 찾을 수 없다는 메시지를 표시한다", async () => {
    mockListIncidents.mockResolvedValue(incidents);
    mockGetImpactDag.mockResolvedValue(dag);

    renderAt("999");

    expect(await screen.findByText(/사건을 찾을 수 없습니다/)).toBeInTheDocument();
  });
});
