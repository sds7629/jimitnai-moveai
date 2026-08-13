import { describe, expect, it } from "vitest";
import { layoutDagIntoColumns } from "../layout";
import type { ImpactDagEdgeApi, ImpactDagNodeApi } from "../types";

function node(overrides: Partial<ImpactDagNodeApi> & { id: number; node_key: string; label: string }): ImpactDagNodeApi {
  return {
    snapshot_id: 1,
    affected_target: null,
    expected_time: null,
    basis: null,
    responsible_party: null,
    uncertainty: null,
    created_at: "2026-08-13T00:00:00Z",
    ...overrides,
  };
}

function edge(from_node_id: number, to_node_id: number): ImpactDagEdgeApi {
  return { id: from_node_id * 100 + to_node_id, snapshot_id: 1, from_node_id, to_node_id, basis: null, created_at: "2026-08-13T00:00:00Z" };
}

describe("layoutDagIntoColumns — 정상 시나리오(happy path)", () => {
  it("선형 체인(A→B→C)은 노드 1개짜리 컬럼 3개로 배치된다", () => {
    const nodes = [
      node({ id: 1, node_key: "a", label: "A" }),
      node({ id: 2, node_key: "b", label: "B" }),
      node({ id: 3, node_key: "c", label: "C" }),
    ];
    const edges = [edge(1, 2), edge(2, 3)];

    const columns = layoutDagIntoColumns(nodes, edges);

    expect(columns).toHaveLength(3);
    expect(columns[0].nodes.map((n) => n.label)).toEqual(["A"]);
    expect(columns[1].nodes.map((n) => n.label)).toEqual(["B"]);
    expect(columns[2].nodes.map((n) => n.label)).toEqual(["C"]);
  });

  it("들어오는 엣지가 없는 노드는 트리거로 표시된다", () => {
    const nodes = [node({ id: 1, node_key: "a", label: "A" }), node({ id: 2, node_key: "b", label: "B" })];
    const edges = [edge(1, 2)];

    const columns = layoutDagIntoColumns(nodes, edges);

    expect(columns[0].nodes[0].isTrigger).toBe(true);
    expect(columns[1].nodes[0].isTrigger).toBeFalsy();
  });
});

describe("layoutDagIntoColumns — 분기 구조", () => {
  it("fan-out(A→B, A→C)은 B/C가 같은 컬럼에 배치된다", () => {
    const nodes = [
      node({ id: 1, node_key: "a", label: "A" }),
      node({ id: 2, node_key: "b", label: "B" }),
      node({ id: 3, node_key: "c", label: "C" }),
    ];
    const edges = [edge(1, 2), edge(1, 3)];

    const columns = layoutDagIntoColumns(nodes, edges);

    expect(columns).toHaveLength(2);
    expect(columns[1].nodes.map((n) => n.label).sort()).toEqual(["B", "C"]);
  });

  it("fan-in(B→D, C→D)은 D가 B/C보다 뒤 컬럼에 배치된다(더 긴 경로 기준)", () => {
    const nodes = [
      node({ id: 1, node_key: "a", label: "A" }),
      node({ id: 2, node_key: "b", label: "B" }),
      node({ id: 3, node_key: "c", label: "C" }),
      node({ id: 4, node_key: "d", label: "D" }),
    ];
    // A→B→D (길이 2), A→C→D (길이 2), C는 A에서 바로, D는 B/C 둘 다에서 옴
    const edges = [edge(1, 2), edge(1, 3), edge(2, 4), edge(3, 4)];

    const columns = layoutDagIntoColumns(nodes, edges);

    expect(columns).toHaveLength(3);
    expect(columns[2].nodes.map((n) => n.label)).toEqual(["D"]);
  });
});

describe("layoutDagIntoColumns — 경계값", () => {
  it("엣지가 하나도 없으면 모든 노드가 트리거로 1개 컬럼에 배치된다", () => {
    const nodes = [node({ id: 1, node_key: "a", label: "A" }), node({ id: 2, node_key: "b", label: "B" })];

    const columns = layoutDagIntoColumns(nodes, []);

    expect(columns).toHaveLength(1);
    expect(columns[0].nodes.every((n) => n.isTrigger)).toBe(true);
  });

  it("노드가 0개면 빈 배열을 반환한다", () => {
    expect(layoutDagIntoColumns([], [])).toEqual([]);
  });
});

describe("layoutDagIntoColumns — 필드 매핑", () => {
  it("basis/uncertainty/responsible_party/affected_target/expected_time을 detail로 매핑한다", () => {
    const nodes = [
      node({
        id: 1,
        node_key: "a",
        label: "A",
        basis: "근거텍스트",
        uncertainty: "low",
        responsible_party: "공장 운영팀",
        affected_target: "PT-001",
        expected_time: "2026-08-13T01:00:00Z",
      }),
    ];

    const columns = layoutDagIntoColumns(nodes, []);
    const detail = columns[0].nodes[0].detail;

    expect(detail).toEqual({
      basis: "근거텍스트",
      uncertainty: "low",
      responsibleParty: "공장 운영팀",
      affectedTarget: "PT-001",
      expectedTime: "2026-08-13T01:00:00Z",
    });
  });
});
