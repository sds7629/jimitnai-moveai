import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { IncidentDetailPage } from "../IncidentDetailPage";
import { listIncidents } from "../../features/incidents/api";
import { getImpactDag } from "../../features/impact-dag/api";
import { getLatestSnapshot } from "../../features/snapshot/api";
import { listCandidates, runSimulation } from "../../features/candidates/api";
import { getDecisionPackage } from "../../features/decision-package/api";
import { submitApproval } from "../../features/approvals/api";
import { useIncidentStream } from "../../features/stream/useIncidentStream";
import { dispatchSop, getSopStatus } from "../../features/sop-dispatch/api";
import { getTimeline, updateSopStatus } from "../../features/execution-tracking/api";
import type { IncidentListItem } from "../../features/incidents/types";
import type { ImpactDagApiResponse } from "../../features/impact-dag/types";
import type { OperationalSnapshotApi } from "../../features/snapshot/types";
import type { CandidateApi, CandidatesListResponse } from "../../features/candidates/types";
import type { DecisionPackageApi } from "../../features/decision-package/types";
import type { IncidentStreamHandlers } from "../../features/stream/useIncidentStream";

vi.mock("../../features/incidents/api");
vi.mock("../../features/impact-dag/api");
vi.mock("../../features/snapshot/api");
vi.mock("../../features/candidates/api");
vi.mock("../../features/decision-package/api");
vi.mock("../../features/approvals/api");
vi.mock("../../features/stream/useIncidentStream");
vi.mock("../../features/sop-dispatch/api");
vi.mock("../../features/execution-tracking/api");
const mockListIncidents = vi.mocked(listIncidents);
const mockGetImpactDag = vi.mocked(getImpactDag);
const mockGetLatestSnapshot = vi.mocked(getLatestSnapshot);
const mockListCandidates = vi.mocked(listCandidates);
const mockRunSimulation = vi.mocked(runSimulation);
const mockGetDecisionPackage = vi.mocked(getDecisionPackage);
const mockSubmitApproval = vi.mocked(submitApproval);
const mockUseIncidentStream = vi.mocked(useIncidentStream);
const mockDispatchSop = vi.mocked(dispatchSop);
const mockGetSopStatus = vi.mocked(getSopStatus);
const mockGetTimeline = vi.mocked(getTimeline);
const mockUpdateSopStatus = vi.mocked(updateSopStatus);

// 이 파일 뒤쪽 테스트들이 mockDispatchSop.not.toHaveBeenCalled() 같은 음성 단언을 쓰기 때문에,
// 이전 테스트의 호출 이력이 남아있으면 안 된다.
beforeEach(() => {
  vi.clearAllMocks();
});

/** useIncidentStream(incidentId, handlers) 호출에 넘겨진 handlers를 꺼내는 헬퍼 */
function getStreamHandlers(): IncidentStreamHandlers {
  const calls = mockUseIncidentStream.mock.calls;
  const call = calls[calls.length - 1];
  if (!call) throw new Error("useIncidentStream이 호출되지 않았습니다");
  return call[1];
}

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

const decisionPackage: DecisionPackageApi = {
  id: 1,
  incident_id: 2,
  recommended_deadline: null,
  created_at: "2026-08-13T02:00:00Z",
  package: {
    expected_loss_p90_cvar: {},
    now_vs_6h_vs_no_action: {},
    causal_path: {},
    data_and_documents_used: {},
    fact_inference_assumption: {},
    freshness_and_coverage: {},
    key_sensitivity_variables: {},
    feasibility_and_exclusion: {},
    confidence_and_uncertainty: {},
    ranked_candidates: {},
    disclaimer: "이 패키지는 대응안의 순위와 근거를 제공할 뿐입니다.",
  },
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

function mockAllSuccess() {
  mockListIncidents.mockResolvedValue(incidents);
  mockGetImpactDag.mockResolvedValue(dag);
  mockGetLatestSnapshot.mockResolvedValue(snapshot);
  mockListCandidates.mockResolvedValue(candidatesResponse);
  mockGetDecisionPackage.mockResolvedValue(decisionPackage);
  mockGetSopStatus.mockResolvedValue({ incident_id: 2, sop_statuses: [] });
  mockGetTimeline.mockResolvedValue({ incident_id: 2, events: [] });
}

describe("IncidentDetailPage — 정상 시나리오(happy path)", () => {
  it("사건 정보·DAG·스냅샷·대응안 후보·의사결정 근거를 함께 불러와 대시보드를 렌더링한다", async () => {
    mockAllSuccess();

    renderAt("2");

    expect(await screen.findByText("항만 파업")).toBeInTheDocument();
    expect(screen.getByText("항만/운송 노동 파업")).toBeInTheDocument();
    expect(screen.getByText("데이터 버전 v1")).toBeInTheDocument();
    expect(screen.getByText("안전재고 사전 당김")).toBeInTheDocument();
    expect(screen.getByText("이 패키지는 대응안의 순위와 근거를 제공할 뿐입니다.")).toBeInTheDocument();
  });
});

describe("IncidentDetailPage — 로딩 상태", () => {
  it("응답이 오기 전에는 로딩 문구를 표시한다", () => {
    mockListIncidents.mockReturnValue(new Promise(() => {}));
    mockGetImpactDag.mockReturnValue(new Promise(() => {}));
    mockGetLatestSnapshot.mockReturnValue(new Promise(() => {}));
    mockListCandidates.mockReturnValue(new Promise(() => {}));
    mockGetDecisionPackage.mockReturnValue(new Promise(() => {}));
    mockGetSopStatus.mockReturnValue(new Promise(() => {}));
    mockGetTimeline.mockReturnValue(new Promise(() => {}));

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

  it("의사결정 근거 조회가 실패해도 에러 메시지를 표시한다", async () => {
    mockAllSuccess();
    mockGetDecisionPackage.mockRejectedValue(new Error("근거 조회 실패"));

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

describe("IncidentDetailPage — 담당자 승인", () => {
  it("승인 폼 제출 시 POST /approvals를 한글 decision_type으로 호출한다", async () => {
    const user = userEvent.setup();
    mockAllSuccess();
    mockSubmitApproval.mockResolvedValue({
      id: 1,
      incident_id: 2,
      decision_type: "승인",
      reason: "재고 확보 완료",
      approver: "김담당",
      decided_at: "2026-08-13T03:00:00Z",
      data_version_ref: "v1",
      scenario_version_ref: "strike-v1",
      created_at: "2026-08-13T03:00:00Z",
    });

    renderAt("2");
    await screen.findByText("안전재고 사전 당김");

    await user.type(screen.getByLabelText("승인자"), "김담당");
    await user.type(screen.getByLabelText("사유"), "재고 확보 완료");
    await user.click(screen.getByRole("button", { name: "승인" }));

    expect(mockSubmitApproval).toHaveBeenCalledWith(2, {
      decision_type: "승인",
      reason: "재고 확보 완료",
      approver: "김담당",
    });
  });

  it("승인 제출이 실패하면 에러 문구를 보여주고 기존 화면은 유지한다", async () => {
    const user = userEvent.setup();
    mockAllSuccess();
    mockSubmitApproval.mockRejectedValue(new Error("검증 실패"));

    renderAt("2");
    await screen.findByText("안전재고 사전 당김");

    await user.type(screen.getByLabelText("승인자"), "김담당");
    await user.type(screen.getByLabelText("사유"), "사유 텍스트");
    await user.click(screen.getByRole("button", { name: "승인" }));

    expect(await screen.findByText(/제출 실패/)).toBeInTheDocument();
    expect(screen.getByText("안전재고 사전 당김")).toBeInTheDocument();
  });
});

describe("IncidentDetailPage — SSE 실시간 갱신", () => {
  it("useIncidentStream을 현재 사건 ID로 구독한다", async () => {
    mockAllSuccess();
    renderAt("2");
    await screen.findByText("안전재고 사전 당김");

    expect(mockUseIncidentStream).toHaveBeenCalledWith(2, expect.any(Object));
  });

  it("dag_updated 이벤트가 오면 DAG·스냅샷을 다시 불러온다", async () => {
    mockAllSuccess();
    renderAt("2");
    await screen.findByText("항만/운송 노동 파업");

    mockGetImpactDag.mockResolvedValue({
      ...dag,
      nodes: [{ ...dag.nodes[0], label: "갱신된 노드" }],
    });

    await act(async () => {
      getStreamHandlers().onDagUpdated?.();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(await screen.findByText("갱신된 노드")).toBeInTheDocument();
  });

  it("decision_package_updated 이벤트가 오면 의사결정 근거를 다시 불러온다", async () => {
    mockAllSuccess();
    renderAt("2");
    await screen.findByText("이 패키지는 대응안의 순위와 근거를 제공할 뿐입니다.");

    mockGetDecisionPackage.mockResolvedValue({
      ...decisionPackage,
      package: { ...decisionPackage.package, disclaimer: "갱신된 면책 문구" },
    });

    await act(async () => {
      getStreamHandlers().onDecisionPackageUpdated?.();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(await screen.findByText("갱신된 면책 문구")).toBeInTheDocument();
  });

  it("deadline_overrun 이벤트가 오면 경고 배너를 표시한다", async () => {
    mockAllSuccess();
    renderAt("2");
    await screen.findByText("안전재고 사전 당김");

    act(() => {
      getStreamHandlers().onDeadlineOverrun?.();
    });

    expect(await screen.findByText(/결정기한이 초과되어/)).toBeInTheDocument();
  });
});

describe("IncidentDetailPage — SOP 자동 발송", () => {
  it("승인이 성공하면 dispatch-sop을 호출하고 발송 상태를 다시 불러온다", async () => {
    const user = userEvent.setup();
    mockAllSuccess();
    mockSubmitApproval.mockResolvedValue({
      id: 42,
      incident_id: 2,
      decision_type: "승인",
      reason: "재고 확보 완료",
      approver: "김담당",
      decided_at: "2026-08-13T03:00:00Z",
      data_version_ref: "v1",
      scenario_version_ref: "strike-v1",
      created_at: "2026-08-13T03:00:00Z",
    });
    mockDispatchSop.mockResolvedValue([]);

    renderAt("2");
    await screen.findByText("안전재고 사전 당김");

    mockGetSopStatus.mockResolvedValue({
      incident_id: 2,
      sop_statuses: [
        {
          sop_id: 1,
          incident_id: 2,
          role: "항만",
          approval_id: 42,
          action_summary: "우선 반출 대상 컨테이너 처리",
          dispatched_at: "2026-08-13T03:00:00Z",
          dispatched_by: "김담당",
          status: "발송",
          received_at: null,
          accepted_at: null,
          completed_at: null,
          failed_at: null,
          events: [],
        },
      ],
    });

    await user.type(screen.getByLabelText("승인자"), "김담당");
    await user.type(screen.getByLabelText("사유"), "재고 확보 완료");
    await user.click(screen.getByRole("button", { name: "승인" }));

    expect(await screen.findByText("우선 반출 대상 컨테이너 처리")).toBeInTheDocument();
    expect(mockDispatchSop).toHaveBeenCalledWith(42);
  });

  it("반려는 SOP를 발송하지 않는다", async () => {
    const user = userEvent.setup();
    mockAllSuccess();
    mockSubmitApproval.mockResolvedValue({
      id: 43,
      incident_id: 2,
      decision_type: "반려",
      reason: "반려 사유입니다",
      approver: "김담당",
      decided_at: "2026-08-13T03:00:00Z",
      data_version_ref: "v1",
      scenario_version_ref: "strike-v1",
      created_at: "2026-08-13T03:00:00Z",
    });

    renderAt("2");
    await screen.findByText("안전재고 사전 당김");

    await user.type(screen.getByLabelText("승인자"), "김담당");
    await user.type(screen.getByLabelText("사유"), "반려 사유입니다");
    await user.click(screen.getByRole("button", { name: "반려" }));

    await screen.findByText("안전재고 사전 당김");
    expect(mockDispatchSop).not.toHaveBeenCalled();
  });

  it("SOP 발송이 실패해도 승인 자체는 성공한 화면을 유지한다", async () => {
    const user = userEvent.setup();
    mockAllSuccess();
    mockSubmitApproval.mockResolvedValue({
      id: 44,
      incident_id: 2,
      decision_type: "승인",
      reason: "재고 확보 완료",
      approver: "김담당",
      decided_at: "2026-08-13T03:00:00Z",
      data_version_ref: "v1",
      scenario_version_ref: "strike-v1",
      created_at: "2026-08-13T03:00:00Z",
    });
    mockDispatchSop.mockRejectedValue(new Error("발송 실패"));

    renderAt("2");
    await screen.findByText("안전재고 사전 당김");

    await user.type(screen.getByLabelText("승인자"), "김담당");
    await user.type(screen.getByLabelText("사유"), "재고 확보 완료");
    await user.click(screen.getByRole("button", { name: "승인" }));

    // 승인 자체는 성공했으므로 제출 실패 메시지 없이 기존 화면이 유지된다
    await screen.findByText("안전재고 사전 당김");
    expect(screen.queryByText(/제출 실패/)).not.toBeInTheDocument();
  });
});

const dispatchedSop = {
  sop_id: 9,
  incident_id: 2,
  role: "항만",
  approval_id: 42,
  action_summary: "우선 반출 대상 컨테이너 처리",
  dispatched_at: "2026-08-13T03:00:00Z",
  dispatched_by: "김담당",
  status: "발송",
  received_at: null,
  accepted_at: null,
  completed_at: null,
  failed_at: null,
  events: [],
};

describe("IncidentDetailPage — SOP 상태 전이 및 타임라인", () => {
  it("상태 전이 성공 시 PATCH를 호출하고 SOP 상태·타임라인을 다시 불러온다", async () => {
    const user = userEvent.setup();
    mockAllSuccess();
    mockGetSopStatus.mockResolvedValue({ incident_id: 2, sop_statuses: [dispatchedSop] });

    renderAt("2");
    await screen.findByText("항만");

    mockUpdateSopStatus.mockResolvedValue({
      id: 100,
      incident_id: 2,
      sop_id: 9,
      status: "수신",
      actor: "박현장",
      note: null,
      created_at: "2026-08-13T04:00:00Z",
      deviation_check: null,
    });
    mockGetSopStatus.mockResolvedValue({ incident_id: 2, sop_statuses: [{ ...dispatchedSop, status: "수신" }] });
    mockGetTimeline.mockResolvedValue({
      incident_id: 2,
      events: [
        {
          id: 1,
          event_type: "sop_status_changed",
          actor: "박현장",
          reason: null,
          sop_id: 9,
          status: "수신",
          payload: {},
          created_at: "2026-08-13T04:00:00Z",
          is_deviation_event: false,
        },
      ],
    });

    await user.type(screen.getByLabelText("실행자"), "박현장");
    await user.click(screen.getByRole("button", { name: "수신" }));

    expect(mockUpdateSopStatus).toHaveBeenCalledWith(9, { status: "수신", actor: "박현장" });
    expect(await screen.findByText("sop_status_changed")).toBeInTheDocument();
  });

  it("편차가 감지되면(deviation_check 존재) DAG·후보·의사결정 패키지도 다시 불러온다", async () => {
    const user = userEvent.setup();
    mockAllSuccess();
    mockGetSopStatus.mockResolvedValue({ incident_id: 2, sop_statuses: [dispatchedSop] });

    renderAt("2");
    await screen.findByText("항만");

    mockUpdateSopStatus.mockResolvedValue({
      id: 101,
      incident_id: 2,
      sop_id: 9,
      status: "실패",
      actor: "박현장",
      note: null,
      created_at: "2026-08-13T04:00:00Z",
      deviation_check: { triggered: true },
    });
    mockGetSopStatus.mockResolvedValue({ incident_id: 2, sop_statuses: [{ ...dispatchedSop, status: "실패" }] });
    mockGetTimeline.mockResolvedValue({ incident_id: 2, events: [] });
    mockGetImpactDag.mockResolvedValue({ ...dag, nodes: [{ ...dag.nodes[0], label: "재계산된 노드" }] });

    await user.type(screen.getByLabelText("실행자"), "박현장");
    await user.click(screen.getByRole("button", { name: "실패" }));

    expect(await screen.findByText("재계산된 노드")).toBeInTheDocument();
  });

  it("상태 전이가 실패하면 에러 문구를 보여주고 기존 화면은 유지한다", async () => {
    const user = userEvent.setup();
    mockAllSuccess();
    mockGetSopStatus.mockResolvedValue({ incident_id: 2, sop_statuses: [dispatchedSop] });

    renderAt("2");
    await screen.findByText("항만");

    mockUpdateSopStatus.mockRejectedValue(new Error("상태 전이 실패"));

    await user.type(screen.getByLabelText("실행자"), "박현장");
    await user.click(screen.getByRole("button", { name: "수신" }));

    expect(await screen.findByText(/상태 갱신 실패/)).toBeInTheDocument();
    expect(screen.getByText("항만")).toBeInTheDocument();
  });
});
