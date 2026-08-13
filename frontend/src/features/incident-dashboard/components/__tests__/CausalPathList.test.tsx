import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { CausalPathList } from "../CausalPathList";
import type { CausalPathSection } from "../../../decision-package/types";

describe("CausalPathList — 정상 시나리오(happy path)", () => {
  it("노드를 순서 번호가 붙은 리스트로, basis/uncertainty와 함께 렌더링한다", () => {
    const section: CausalPathSection = {
      nodes: [
        {
          node_key: "trigger",
          label: "부산항 하역 지연",
          affected_target: "부산항 3번 선석",
          expected_time: "2026-08-13T00:00:00Z",
          basis: "관세청 통관 지연 공지",
          responsible_party: "부산항만공사",
          uncertainty: "낮음",
        },
        {
          node_key: "impact-1",
          label: "A공장 재고 소진",
          affected_target: "A공장 생산라인",
          expected_time: "2026-08-13T06:00:00Z",
          basis: "재고 회전율 시뮬레이션",
          responsible_party: null,
          uncertainty: "중간",
        },
      ],
      edges: [{ from_node_key: "trigger", to_node_key: "impact-1", basis: "리드타임 계산" }],
    };

    render(<CausalPathList section={section} />);

    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("부산항 하역 지연")).toBeInTheDocument();
    expect(screen.getByText("A공장 재고 소진")).toBeInTheDocument();
    expect(screen.getByText(/관세청 통관 지연 공지/)).toBeInTheDocument();
    expect(screen.getByText(/낮음/)).toBeInTheDocument();
    expect(screen.getByText(/리드타임 계산/)).toBeInTheDocument();
  });
});

describe("CausalPathList — 경계값(단일 노드, 엣지 없음)", () => {
  it("노드가 하나면 엣지 화살표 없이 노드 하나만 표시한다", () => {
    const section: CausalPathSection = {
      nodes: [
        {
          node_key: "only",
          label: "단일 노드",
          affected_target: null,
          expected_time: null,
          basis: null,
          responsible_party: null,
          uncertainty: null,
        },
      ],
      edges: [],
    };

    render(<CausalPathList section={section} />);

    expect(screen.getByText("단일 노드")).toBeInTheDocument();
    expect(screen.queryByText("2")).not.toBeInTheDocument();
  });
});

describe("CausalPathList — 실패 시나리오(빈 경로)", () => {
  it("노드가 없으면 안내 문구를 표시한다", () => {
    render(<CausalPathList section={{ nodes: [], edges: [] }} />);
    expect(screen.getByText("영향 전파 경로가 없습니다.")).toBeInTheDocument();
  });
});
