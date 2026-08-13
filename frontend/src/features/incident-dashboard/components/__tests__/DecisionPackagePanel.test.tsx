import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DecisionPackagePanel } from "../DecisionPackagePanel";
import type { DecisionPackageApi } from "../../../decision-package/types";

const samplePackage: DecisionPackageApi = {
  id: 1,
  incident_id: 2,
  recommended_deadline: "2026-08-13T02:00:00Z",
  created_at: "2026-08-13T00:00:00Z",
  package: {
    expected_loss_p90_cvar: { "1": { candidate_type: "baseline", expected_loss: 200000000 } },
    now_vs_6h_vs_no_action: { no_action: null, now: null, plus_6h: null },
    causal_path: { nodes: [], edges: [] },
    data_and_documents_used: { data_version: "v1", scenario_version: "s1" },
    fact_inference_assumption: {},
    freshness_and_coverage: { quality_mode: "normal", freshness_seconds: 100, coverage_ratio: 1 },
    key_sensitivity_variables: {},
    feasibility_and_exclusion: {},
    confidence_and_uncertainty: {},
    ranked_candidates: { ranked: [], excluded_from_ranking: [] },
    disclaimer: "이 패키지는 대응안의 순위와 근거를 제공할 뿐, 특정 대응안을 정답으로 단정하지 않습니다.",
  },
};

describe("DecisionPackagePanel — 정상 시나리오(happy path)", () => {
  it("면책 문구와 10개 섹션 라벨, 결정기한을 모두 표시한다", () => {
    render(<DecisionPackagePanel decisionPackage={samplePackage} now={new Date("2026-08-13T00:00:00Z")} />);

    expect(screen.getByText(/특정 대응안을 정답으로 단정하지 않습니다/)).toBeInTheDocument();
    expect(screen.getByText("기대손실·P90·CVaR·신뢰도")).toBeInTheDocument();
    expect(screen.getByText("실행 가능성·제외 사유")).toBeInTheDocument();
    expect(screen.getByText(/2시간 후/)).toBeInTheDocument();
  });

  it("기대손실·P90·CVaR 섹션은 JSON이 아니라 표로 렌더링한다", () => {
    render(<DecisionPackagePanel decisionPackage={samplePackage} now={new Date("2026-08-13T00:00:00Z")} />);

    // 표의 후보명 셀로 렌더링되어야 하고, 더 이상 별도의 "기대손실·P90·CVaR" 단독 라벨(구 버전)은 없다
    expect(screen.getByText("baseline")).toBeInTheDocument();
    expect(screen.queryByText("기대손실·P90·CVaR")).not.toBeInTheDocument();
  });

  it("섹션 안의 실제 값을 렌더링한다", () => {
    render(<DecisionPackagePanel decisionPackage={samplePackage} now={new Date("2026-08-13T00:00:00Z")} />);
    expect(screen.getByText(/normal/)).toBeInTheDocument();
  });
});

describe("DecisionPackagePanel — 결정기한 초과", () => {
  it("기한이 지났으면 경고 스타일로 '결정기한 초과'를 표시한다", () => {
    render(
      <DecisionPackagePanel
        decisionPackage={{ ...samplePackage, recommended_deadline: "2026-08-12T00:00:00Z" }}
        now={new Date("2026-08-13T00:00:00Z")}
      />,
    );
    expect(screen.getByText("결정기한 초과")).toBeInTheDocument();
  });
});

describe("DecisionPackagePanel — 경계값(빈 패키지)", () => {
  it("섹션 값이 비어 있어도 오류 없이 렌더링된다", () => {
    render(
      <DecisionPackagePanel
        decisionPackage={{ ...samplePackage, package: {}, recommended_deadline: null }}
        now={new Date("2026-08-13T00:00:00Z")}
      />,
    );
    expect(screen.getByText("결정기한 미산정")).toBeInTheDocument();
  });
});
