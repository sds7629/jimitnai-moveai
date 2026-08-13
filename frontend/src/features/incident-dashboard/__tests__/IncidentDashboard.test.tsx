import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
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
  it("근거 상세가 있는 DAG 노드를 클릭하면 상세 패널의 펼침/접힘 상태(grid-rows)가 토글된다", async () => {
    // CSS grid-rows 트릭으로 애니메이션하므로 콘텐츠는 항상 DOM에 남아있고, grid-rows 클래스만 바뀐다
    // (완전히 사라지는 것이 아니라 높이가 0으로 트랜지션된다).
    const user = userEvent.setup();
    render(<IncidentDashboard data={strikeScenarioMock} />);

    const detailWrapper = screen
      .getByText(/불확실성: medium/)
      .closest('[data-testid="dag-node-detail-wrapper"]') as HTMLElement;

    // 기본값은 펼쳐진 상태
    expect(detailWrapper).toBeInTheDocument();
    expect(detailWrapper.className).toContain("grid-rows-[1fr]");

    const dagNode = screen.getByText("PCTC 해상운송 부산→유럽").closest("div")!;
    await user.click(dagNode);
    expect(detailWrapper.className).toContain("grid-rows-[0fr]");
    // 접혀도 콘텐츠 자체는 DOM에 남아있다
    expect(screen.getByText(/불확실성: medium/)).toBeInTheDocument();

    await user.click(dagNode);
    expect(detailWrapper.className).toContain("grid-rows-[1fr]");
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

  it("사유·승인자 입력 후 승인 액션 버튼 클릭 시 선택한 action과 함께 onApprovalSubmit이 호출된다", async () => {
    const user = userEvent.setup();
    const onApprovalSubmit = vi.fn();
    render(<IncidentDashboard data={strikeScenarioMock} onApprovalSubmit={onApprovalSubmit} />);

    await user.type(screen.getByLabelText("승인자"), "김담당");
    await user.type(screen.getByLabelText("사유"), "반려 사유입니다");
    await user.click(screen.getByRole("button", { name: "반려" }));

    expect(onApprovalSubmit).toHaveBeenCalledWith("reject", "반려 사유입니다", "김담당");
  });
});

describe("IncidentDashboard — 경계값/예외 케이스", () => {
  it("제외된 대응안이 없으면 '제외된 대응안' 섹션 자체를 렌더링하지 않는다", () => {
    render(<IncidentDashboard data={{ ...strikeScenarioMock, excludedCandidates: [] }} />);
    expect(screen.queryByText("제외된 대응안")).not.toBeInTheDocument();
  });

  it("steps가 없는 SOP는 클릭해도 펼쳐지지 않는다(비인터랙티브 항목)", async () => {
    // mockData의 실제 SOP 6건은 모두 steps가 채워져 있으므로(SOP-AIR-02 포함), 이 회귀 테스트는
    // steps가 없는 합성 SOP를 별도로 주입해 SopItem의 비인터랙티브 동작 자체를 검증한다.
    const user = userEvent.setup();
    const dataWithStaticSop = {
      ...strikeScenarioMock,
      sops: [
        ...strikeScenarioMock.sops,
        { code: "SOP-TEST-99", title: "테스트용 비인터랙티브 SOP", owningTeam: "QA팀" },
      ],
    };
    render(<IncidentDashboard data={dataWithStaticSop} />);

    const staticSop = screen.getByText(/SOP-TEST-99/).closest("div")!;
    await user.click(staticSop);
    // 펼칠 절차 목록이 없으므로 클릭해도 오류 없이 그대로 유지된다
    expect(screen.queryByText(/QA팀/)).toBeInTheDocument();
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

describe("IncidentDashboard — 결정기한 초과 배너 (SSE deadline_overrun)", () => {
  it("deadlineOverrunNotice가 true면 경고 배너를 표시한다", () => {
    render(<IncidentDashboard data={strikeScenarioMock} deadlineOverrunNotice />);
    expect(screen.getByText(/결정기한이 초과되어/)).toBeInTheDocument();
  });

  it("deadlineOverrunNotice가 없으면 배너를 표시하지 않는다", () => {
    render(<IncidentDashboard data={strikeScenarioMock} />);
    expect(screen.queryByText(/결정기한이 초과되어/)).not.toBeInTheDocument();
  });
});

describe("IncidentDashboard — SOP 발송 상태 패널", () => {
  it("sopStatuses prop이 있으면(빈 배열 포함) 패널을 렌더링한다", () => {
    render(<IncidentDashboard data={strikeScenarioMock} sopStatuses={[]} />);
    expect(screen.getByText("역할별 SOP 발송 상태")).toBeInTheDocument();
  });

  it("sopStatuses prop이 없으면 패널을 렌더링하지 않는다", () => {
    render(<IncidentDashboard data={strikeScenarioMock} />);
    expect(screen.queryByText("역할별 SOP 발송 상태")).not.toBeInTheDocument();
  });
});

describe("IncidentDashboard — 실행 추적 타임라인", () => {
  it("timelineEvents prop이 있으면 타임라인 섹션을 렌더링한다", () => {
    render(<IncidentDashboard data={strikeScenarioMock} timelineEvents={[]} />);
    expect(screen.getByText("실행 추적 타임라인")).toBeInTheDocument();
  });

  it("timelineEvents prop이 없으면 타임라인 섹션을 렌더링하지 않는다", () => {
    render(<IncidentDashboard data={strikeScenarioMock} />);
    expect(screen.queryByText("실행 추적 타임라인")).not.toBeInTheDocument();
  });
});

describe("IncidentDashboard — 사후보고서 링크", () => {
  it("postReportHref가 있으면 해당 경로로 이동하는 링크를 렌더링한다", () => {
    render(
      <MemoryRouter>
        <IncidentDashboard data={strikeScenarioMock} postReportHref="/incidents/2/post-report" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "사후보고서 보기" })).toHaveAttribute(
      "href",
      "/incidents/2/post-report",
    );
  });

  it("postReportHref가 없으면 링크를 렌더링하지 않는다", () => {
    render(<IncidentDashboard data={strikeScenarioMock} />);
    expect(screen.queryByText("사후보고서 보기")).not.toBeInTheDocument();
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
