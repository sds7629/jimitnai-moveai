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
    causal_path: {
      nodes: [
        {
          node_key: "trigger",
          label: "부산항 하역 지연",
          affected_target: null,
          expected_time: null,
          basis: null,
          responsible_party: null,
          uncertainty: null,
        },
      ],
      edges: [],
    },
    data_and_documents_used: {
      operational_assumptions: ["항만 재개방 시점 미확정"],
      data_version: "v1",
      scenario_version: "s1",
      reference_document_ids_by_candidate: { "1": ["doc-a"] },
    },
    fact_inference_assumption: { "1": { fact: { port_status: "폐쇄" }, inference: {}, assumption: {} } },
    freshness_and_coverage: { quality_mode: "normal", freshness_seconds: 100, coverage_ratio: 1 },
    key_sensitivity_variables: { "1": ["항만 재개방 시점"] },
    feasibility_and_exclusion: {
      "1": {
        validation_status: "가능",
        exclusion_category: null,
        exclusion_detail: null,
        preconditions: ["창고 여유 확보"],
        has_simulation_result: true,
      },
    },
    confidence_and_uncertainty: {},
    ranked_candidates: {
      ranked: [
        {
          candidate_id: 1,
          candidate_type: "baseline",
          description: "기준 시나리오",
          start_time_variant: null,
          validation_status: "가능",
          preconditions: [],
          expected_loss: 200000000,
          p90: 250000000,
          cvar: 300000000,
          risk_score: 235000000,
          feasibility_penalty: 0,
          composite_score: 235000000,
          rank: 1,
        },
      ],
      excluded_from_ranking: [],
    },
    disclaimer: "이 패키지는 대응안의 순위와 근거를 제공할 뿐, 특정 대응안을 정답으로 단정하지 않습니다.",
  },
};

describe("DecisionPackagePanel — 정상 시나리오(happy path)", () => {
  it("면책 문구와 10개 섹션 라벨, 결정기한을 모두 표시한다", () => {
    render(<DecisionPackagePanel decisionPackage={samplePackage} now={new Date("2026-08-13T00:00:00Z")} />);

    expect(screen.getByText(/특정 대응안을 정답으로 단정하지 않습니다/)).toBeInTheDocument();
    expect(screen.getByText("기대손실·P90·CVaR·신뢰도")).toBeInTheDocument();
    expect(screen.getAllByText("실행 가능성·제외 사유")).toHaveLength(1);
    expect(screen.getByText(/2시간 후/)).toBeInTheDocument();
  });

  it("now_vs_6h_vs_no_action 섹션은 JSON이 아니라 3장 카드로 렌더링한다", () => {
    render(<DecisionPackagePanel decisionPackage={samplePackage} now={new Date("2026-08-13T00:00:00Z")} />);

    expect(screen.getByText("무대응")).toBeInTheDocument();
    expect(screen.getAllByText(/해당 후보 없음/)).toHaveLength(3);
  });

  it("기대손실·P90·CVaR 섹션은 JSON이 아니라 표로 렌더링한다", () => {
    render(<DecisionPackagePanel decisionPackage={samplePackage} now={new Date("2026-08-13T00:00:00Z")} />);

    // 표의 후보명 셀로 렌더링되어야 하고, 더 이상 별도의 "기대손실·P90·CVaR" 단독 라벨(구 버전)은 없다
    // ranked_candidates 순위 리스트에도 같은 후보명이 나오므로 getAllByText로 확인한다
    expect(screen.getAllByText("baseline").length).toBeGreaterThan(0);
    expect(screen.queryByText("기대손실·P90·CVaR")).not.toBeInTheDocument();
  });

  it("causal_path 섹션은 JSON이 아니라 순서 리스트로 렌더링한다", () => {
    render(<DecisionPackagePanel decisionPackage={samplePackage} now={new Date("2026-08-13T00:00:00Z")} />);
    expect(screen.getByText("영향 전파 경로")).toBeInTheDocument();
    expect(screen.getByText("부산항 하역 지연")).toBeInTheDocument();
  });

  it("data_and_documents_used·fact_inference_assumption·freshness_and_coverage는 근거 패널 하나로 통합 렌더링한다", () => {
    render(<DecisionPackagePanel decisionPackage={samplePackage} now={new Date("2026-08-13T00:00:00Z")} />);
    expect(screen.getByText("이 판단의 근거")).toBeInTheDocument();
    expect(screen.getByText("항만 재개방 시점 미확정")).toBeInTheDocument();
    expect(screen.getByText("doc-a")).toBeInTheDocument();
    expect(screen.getByText(/port_status/)).toBeInTheDocument();
    expect(screen.queryByText("사용한 데이터·문서")).not.toBeInTheDocument();
    expect(screen.queryByText("FACT·INFERENCE·ASSUMPTION")).not.toBeInTheDocument();
    expect(screen.queryByText("데이터 최신성·커버리지")).not.toBeInTheDocument();
  });

  it("feasibility_and_exclusion·key_sensitivity_variables는 JSON이 아니라 표로 렌더링한다", () => {
    render(<DecisionPackagePanel decisionPackage={samplePackage} now={new Date("2026-08-13T00:00:00Z")} />);
    expect(screen.getByText("가능")).toBeInTheDocument();
    expect(screen.getByText("창고 여유 확보")).toBeInTheDocument();
    expect(screen.getByText("항만 재개방 시점")).toBeInTheDocument();
    expect(screen.queryByText("핵심 민감도 변수")).not.toBeInTheDocument();
  });

  it("ranked_candidates 섹션은 JSON이 아니라 순위 리스트로 렌더링하고, 10개 섹션이 전부 실제 UI다", () => {
    render(<DecisionPackagePanel decisionPackage={samplePackage} now={new Date("2026-08-13T00:00:00Z")} />);
    expect(screen.getByText("대응 조합 순위")).toBeInTheDocument();
    expect(screen.getByText(/composite score/)).toBeInTheDocument();
    // Phase 13~18로 10개 섹션이 전부 전용 UI로 옮겨졌으니, 남은 JSON 블록(JSON.stringify pre 태그)이 없어야 한다
    expect(document.querySelectorAll("pre")).toHaveLength(0);
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

  it("causal_path 섹션에 nodes/edges 키 자체가 없어도(빈 객체) 오류 없이 렌더링된다", () => {
    // 회귀 테스트 — 다른 화면(IncidentDashboard/IncidentDetailPage)의 목업 fixture가
    // causal_path: {}처럼 nodes/edges 키를 아예 생략해서 쓰는 경우와 동일한 패턴
    render(
      <DecisionPackagePanel
        decisionPackage={{ ...samplePackage, package: { ...samplePackage.package, causal_path: {} } }}
        now={new Date("2026-08-13T00:00:00Z")}
      />,
    );
    expect(screen.getByText("영향 전파 경로가 없습니다.")).toBeInTheDocument();
  });

  it("data_and_documents_used·freshness_and_coverage 키가 아예 없어도(빈 객체) NaN 없이 렌더링된다", () => {
    // 회귀 테스트 — IncidentDashboard/IncidentDetailPage 기존 fixture가
    // freshness_and_coverage: {}처럼 quality_mode/freshness_seconds/coverage_ratio를
    // 아예 생략해서 쓰는 경우, 필드별 기본값 처리 없이 그대로 포맷하면 "NaN%"가 나온다
    render(
      <DecisionPackagePanel
        decisionPackage={{
          ...samplePackage,
          package: { ...samplePackage.package, data_and_documents_used: {}, freshness_and_coverage: {} },
        }}
        now={new Date("2026-08-13T00:00:00Z")}
      />,
    );
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
    expect(screen.getByText("등록된 가정이 없습니다.")).toBeInTheDocument();
  });
});
