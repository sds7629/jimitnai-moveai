import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { IncidentDetailPage } from "../IncidentDetailPage";
import { listIncidents } from "../../features/incidents/api";
import { getImpactDag } from "../../features/impact-dag/api";
import { getLatestSnapshot } from "../../features/snapshot/api";
import { listCandidates, runSimulation } from "../../features/candidates/api";
import type { IncidentListItem } from "../../features/incidents/types";
import type { ImpactDagApiResponse } from "../../features/impact-dag/types";
import type { OperationalSnapshotApi } from "../../features/snapshot/types";
import type { CandidateApi, CandidatesListResponse } from "../../features/candidates/types";

vi.mock("../../features/incidents/api");
vi.mock("../../features/impact-dag/api");
vi.mock("../../features/snapshot/api");
vi.mock("../../features/candidates/api");
const mockListIncidents = vi.mocked(listIncidents);
const mockGetImpactDag = vi.mocked(getImpactDag);
const mockGetLatestSnapshot = vi.mocked(getLatestSnapshot);
const mockListCandidates = vi.mocked(listCandidates);
const mockRunSimulation = vi.mocked(runSimulation);

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

const snapshot: OperationalSnapshotApi = {
  id: 10,
  incident_id: 2,
  data_version: "v1",
  scenario_version: "strike-v1",
  assumptions: [],
  operational_state: {},
  quality_mode: "normal",
  freshness_seconds: 125,
  coverage_ratio: 1,
  created_at: "2026-08-13T02:00:00Z",
};

const oneCandidate: CandidateApi = {
  id: 1,
  incident_id: 2,
  snapshot_id: 10,
  candidate_type: "안전재고 사전 당김",
  description: "설명",
  reference_document_ids: [],
  preconditions: [],
  start_time_variant: null,
  validation_status: "가능",
  exclusion_category: null,
  exclusion_detail: null,
  created_at: "2026-08-13T02:00:00Z",
  updated_at: "2026-08-13T02:00:00Z",
  latest_simulation: {
    id: 1,
    candidate_id: 1,
    incident_id: 2,
    expected_loss: 100_000_000,
    p90: 150_000_000,
    cvar: 180_000_000,
    sensitivity_variables: [],
    confidence: 0.8,
    fact: {},
    inference: {},
    assumption: {},
    data_version: "v1",
    scenario_version: "strike-v1",
    created_at: "2026-08-13T02:00:00Z",
  },
};

const candidatesResponse: CandidatesListResponse = { incident_id: 2, candidates: [oneCandidate] };

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/incidents/${id}`]}>
      <Routes>
        <Route path="/incidents/:id" element={<IncidentDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function mockAllSuccess() {
  mockListIncidents.mockResolvedValue(incidents);
  mockGetImpactDag.mockResolvedValue(dag);
  mockGetLatestSnapshot.mockResolvedValue(snapshot);
  mockListCandidates.mockResolvedValue(candidatesResponse);
}

describe("IncidentDetailPage — 정상 시나리오(happy path)", () => {
  it("사건 정보·DAG·스냅샷·대응안 후보를 함께 불러와 대시보드를 렌더링한다", async () => {
    mockAllSuccess();

    renderAt("2");

    expect(await screen.findByText("항만 파업")).toBeInTheDocument();
    expect(screen.getByText("항만/운송 노동 파업")).toBeInTheDocument();
    expect(screen.getByText("데이터 버전 v1")).toBeInTheDocument();
    expect(screen.getByText("안전재고 사전 당김")).toBeInTheDocument();
  });
});

describe("IncidentDetailPage — 로딩 상태", () => {
  it("응답이 오기 전에는 로딩 문구를 표시한다", () => {
    mockListIncidents.mockReturnValue(new Promise(() => {}));
    mockGetImpactDag.mockReturnValue(new Promise(() => {}));
    mockGetLatestSnapshot.mockReturnValue(new Promise(() => {}));
    mockListCandidates.mockReturnValue(new Promise(() => {}));

    renderAt("2");

    expect(screen.getByText(/불러오는 중/)).toBeInTheDocument();
  });
});

describe("IncidentDetailPage — 예외 케이스", () => {
  it("DAG 조회가 실패하면 에러 메시지를 표시한다", async () => {
    mockAllSuccess();
    mockGetImpactDag.mockRejectedValue(new Error("DAG 조회 실패"));

    renderAt("2");

    expect(await screen.findByText(/불러오지 못했습니다/)).toBeInTheDocument();
  });

  it("대응안 후보 조회가 실패해도 에러 메시지를 표시한다", async () => {
    mockAllSuccess();
    mockListCandidates.mockRejectedValue(new Error("후보 조회 실패"));

    renderAt("2");

    expect(await screen.findByText(/불러오지 못했습니다/)).toBeInTheDocument();
  });
});

describe("IncidentDetailPage — 경계값(존재하지 않는 사건)", () => {
  it("목록에 없는 id로 접근하면 사건을 찾을 수 없다는 메시지를 표시한다", async () => {
    mockAllSuccess();

    renderAt("999");

    expect(await screen.findByText(/사건을 찾을 수 없습니다/)).toBeInTheDocument();
  });
});

describe("IncidentDetailPage — 다시 실행(재시뮬레이션)", () => {
  it("'다시 실행' 클릭 시 POST /simulate 후 대응안 후보를 다시 불러온다", async () => {
    const user = userEvent.setup();
    mockAllSuccess();
    mockRunSimulation.mockResolvedValue({
      incident_id: 2,
      reused_existing_candidates: true,
      candidate_count: 1,
      validated_count: 1,
      simulated_count: 1,
    });

    renderAt("2");
    await screen.findByText("안전재고 사전 당김");

    const updatedCandidate: CandidateApi = {
      ...oneCandidate,
      latest_simulation: { ...oneCandidate.latest_simulation!, expected_loss: 10_000_000 },
    };
    mockListCandidates.mockResolvedValue({ incident_id: 2, candidates: [updatedCandidate] });

    await user.click(screen.getByRole("button", { name: "다시 실행" }));

    expect(mockRunSimulation).toHaveBeenCalledWith(2);
    expect(await screen.findByText(/0\.1억원/)).toBeInTheDocument();
  });

  it("재시뮬레이션이 실패하면 에러 문구를 보여주고 기존 화면은 유지한다", async () => {
    const user = userEvent.setup();
    mockAllSuccess();
    mockRunSimulation.mockRejectedValue(new Error("LLM 호출 실패"));

    renderAt("2");
    await screen.findByText("안전재고 사전 당김");

    await user.click(screen.getByRole("button", { name: "다시 실행" }));

    expect(await screen.findByText(/재시뮬레이션 실패/)).toBeInTheDocument();
    // 기존 후보 데이터는 그대로 남아있어야 한다
    expect(screen.getByText("안전재고 사전 당김")).toBeInTheDocument();
  });
});
