import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IncidentDashboard } from "../IncidentDashboard";
import { strikeScenarioMock } from "../mockData";
import { CandidateRow } from "../components/CandidateRow";
import type { SnapshotSummary } from "../../snapshot/format";
import type { DecisionPackageApi } from "../../decision-package/types";

const sampleSnapshot: SnapshotSummary = {
  dataVersion: "v1",
  scenarioVersion: "strike-v1",
  qualityModeLabel: "정상",
  freshnessLabel: "5분 전",
  coverageLabel: "100%",
  assumptions: ["가정 A"],
};

const sampleDecisionPackage: DecisionPackageApi = {
  id: 1,
  incident_id: 1,
  recommended_deadline: null,
  created_at: "2026-08-13T00:00:00Z",
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
    disclaimer: "테스트용 면책 문구",
  },
};

describe("IncidentDashboard — 정상 시나리오(happy path)", () => {
  it("헤더/사건 컨텍스트/DAG/대응안/SOP/승인 패널을 모두 렌더링한다", () => {
    render(<IncidentDashboard data={strikeScenarioMock} />);

    expect(screen.getByText("도미노 시뮬레이터")).toBeInTheDocument();
    expect(screen.getByText("생산라인 파업")).toBeInTheDocument();
    expect(screen.getByText("부산신항 HPNT")).toBeInTheDocument();
    expect(screen.getByText("안전재고 사전 당김")).toBeInTheDocument();
    expect(screen.getByText(/SOP-LINE-01/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "승인" })).toBeInTheDocument();
  });

  it("트리거 노드에는 지연/비용 지표를 표시하지 않는다", () => {
    render(<IncidentDashboard data={strikeScenarioMock} />);
    const triggerNode = screen.getByText("부산신항 HPNT").closest("div");
    expect(triggerNode).not.toHaveTextContent("일");
  });
});

describe("IncidentDashboard — prop 기반 상태 분기", () => {
  it("aiStatus에 따라 AI 상태 뱃지 라벨이 바뀐다", () => {
    const { rerender } = render(<IncidentDashboard data={strikeScenarioMock} aiStatus="live" />);
    expect(screen.getByText("AI: 정상")).toBeInTheDocument();

    rerender(<IncidentDashboard data={strikeScenarioMock} aiStatus="degraded" />);
    expect(screen.getByText("AI: 성능저하")).toBeInTheDocument();
  });

  it("대응안 후보가 0건이면 시뮬레이션 미실행 안내를 표시한다", () => {
    render(<IncidentDashboard data={{ ...strikeScenarioMock, candidates: [] }} />);
    expect(screen.getByText(/아직 시뮬레이션 결과가 없습니다/)).toBeInTheDocument();
  });

  it("showSopDemoNote가 false면 데모용 워터마크 문구를 표시하지 않는다", () => {
    render(<IncidentDashboard data={strikeScenarioMock} showSopDemoNote={false} />);
    expect(screen.queryByText(/데모용 예시 SOP/)).not.toBeInTheDocument();
  });
});

describe("IncidentDashboard — 인터랙션", () => {
  it("근거 상세가 있는 DAG 노드를 클릭하면 불확실성/근거 패널이 접힌다/펼쳐진다", async () => {
    const user = userEvent.setup();
    render(<IncidentDashboard data={strikeScenarioMock} />);

    // 기본값은 펼쳐진 상태
    expect(screen.getByText(/불확실성: medium/)).toBeInTheDocument();

    const dagNode = screen.getByText("PCTC 해상운송 부산→유럽").closest("div")!;
    await user.click(dagNode);
    expect(screen.queryByText(/불확실성: medium/)).not.toBeInTheDocument();

    await user.click(dagNode);
    expect(screen.getByText(/불확실성: medium/)).toBeInTheDocument();
  });

  it("'다시 실행' 버튼 클릭 시 onRerun 콜백이 호출된다", async () => {
    const user = userEvent.setup();
    const onRerun = vi.fn();
    render(<IncidentDashboard data={strikeScenarioMock} onRerun={onRerun} />);

    await user.click(screen.getByRole("button", { name: "다시 실행" }));
    expect(onRerun).toHaveBeenCalledTimes(1);
  });

  it("isRerunning이 true면 '다시 실행' 버튼이 비활성화되고 실행 중 문구를 보여준다", () => {
    render(<IncidentDashboard data={strikeScenarioMock} isRerunning />);
    const button = screen.getByRole("button", { name: "실행 중..." });
    expect(button).toBeDisabled();
  });

  it("승인 액션 버튼 클릭 시 선택한 action과 함께 onApprovalAction이 호출된다", async () => {
    const user = userEvent.setup();
    const onApprovalAction = vi.fn();
    render(<IncidentDashboard data={strikeScenarioMock} onApprovalAction={onApprovalAction} />);

    await user.click(screen.getByRole("button", { name: "반려" }));
    expect(onApprovalAction).toHaveBeenCalledWith("reject");
  });
});

describe("IncidentDashboard — 경계값/예외 케이스", () => {
  it("제외된 대응안이 없으면 '제외된 대응안' 섹션 자체를 렌더링하지 않는다", () => {
    render(<IncidentDashboard data={{ ...strikeScenarioMock, excludedCandidates: [] }} />);
    expect(screen.queryByText("제외된 대응안")).not.toBeInTheDocument();
  });

  it("steps가 없는 SOP는 클릭해도 펼쳐지지 않는다(비인터랙티브 항목)", async () => {
    const user = userEvent.setup();
    render(<IncidentDashboard data={strikeScenarioMock} />);

    const staticSop = screen.getByText(/SOP-AIR-02/).closest("div")!;
    await user.click(staticSop);
    // 펼칠 절차 목록이 없으므로 클릭해도 오류 없이 그대로 유지된다
    expect(screen.queryByText(/조달ㆍ물류팀/)).toBeInTheDocument();
  });
});

describe("IncidentDashboard — 운영 스냅샷 상태 바", () => {
  it("snapshot prop이 있으면 데이터 버전/품질 모드/최신성/커버리지를 표시한다", () => {
    render(<IncidentDashboard data={strikeScenarioMock} snapshot={sampleSnapshot} />);

    expect(screen.getByText("데이터 버전 v1")).toBeInTheDocument();
    expect(screen.getByText("정상")).toBeInTheDocument();
    expect(screen.getByText(/5분 전/)).toBeInTheDocument();
    expect(screen.getByText(/100%/)).toBeInTheDocument();
  });

  it("snapshot prop이 없으면 스냅샷 상태 바를 렌더링하지 않는다", () => {
    render(<IncidentDashboard data={strikeScenarioMock} />);
    expect(screen.queryByText(/데이터 버전/)).not.toBeInTheDocument();
  });
});

describe("IncidentDashboard — 의사결정 근거 패널", () => {
  it("decisionPackage prop이 있으면 면책 문구를 표시한다", () => {
    render(<IncidentDashboard data={strikeScenarioMock} decisionPackage={sampleDecisionPackage} />);
    expect(screen.getByText("테스트용 면책 문구")).toBeInTheDocument();
  });

  it("decisionPackage prop이 없으면 의사결정 근거 패널을 렌더링하지 않는다", () => {
    render(<IncidentDashboard data={strikeScenarioMock} />);
    expect(screen.queryByText("의사결정 근거")).not.toBeInTheDocument();
  });
});

describe("IncidentDashboard — 테마 토글", () => {
  it("기본은 다크 테마이고, 우상단 토글 버튼을 클릭하면 라이트로 바뀐다", async () => {
    const user = userEvent.setup();
    const { container } = render(<IncidentDashboard data={strikeScenarioMock} />);

    const root = container.querySelector("[data-theme]");
    expect(root).toHaveAttribute("data-theme", "dark");

    await user.click(screen.getByRole("button", { name: "테마 전환" }));
    expect(root).toHaveAttribute("data-theme", "light");
  });

  it("토글 버튼을 두 번 클릭하면 다시 다크로 돌아온다", async () => {
    const user = userEvent.setup();
    const { container } = render(<IncidentDashboard data={strikeScenarioMock} />);
    const root = container.querySelector("[data-theme]");
    const toggle = screen.getByRole("button", { name: "테마 전환" });

    await user.click(toggle);
    await user.click(toggle);
    expect(root).toHaveAttribute("data-theme", "dark");
  });

  it("theme prop을 light로 넘기면 초기 테마가 라이트로 시작한다", () => {
    const { container } = render(<IncidentDashboard data={strikeScenarioMock} theme="light" />);
    expect(container.querySelector("[data-theme]")).toHaveAttribute("data-theme", "light");
  });
});

describe("CandidateRow — 완화율(mitigationRatio) 경계값 클램핑", () => {
  const base = strikeScenarioMock.candidates[1];

  it("100을 초과하는 값은 100%로 클램핑된다", () => {
    render(<CandidateRow candidate={{ ...base, mitigationRatio: 150 }} />);
    expect(screen.getByTestId("mitigation-bar").style.width).toBe("100%");
  });

  it("0 미만(음수) 값은 0%로 클램핑된다", () => {
    render(<CandidateRow candidate={{ ...base, mitigationRatio: -20 }} />);
    expect(screen.getByTestId("mitigation-bar").style.width).toBe("0%");
  });
});
