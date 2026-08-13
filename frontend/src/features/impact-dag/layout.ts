import type { DagColumn } from "../incident-dashboard/types";
import type { ImpactDagEdgeApi, ImpactDagNodeApi } from "./types";

/**
 * flat한 노드/엣지 목록을 좌→우 컬럼(단계) 배열로 계층화한다.
 *
 * 실제 API(GET /incidents/{id}/impact-dag)는 진짜 그래프(임의의 from/to 엣지 목록)를 주기 때문에,
 * 와이어프레임처럼 미리 그룹핑된 컬럼 구조가 아니다. Kahn의 위상정렬을 이용해 "루트(들어오는 엣지가
 * 없는 노드)로부터의 최장 경로 길이"를 레이어 번호로 삼는다 — 여러 부모를 가진 노드(fan-in)는 가장
 * 늦게 끝나는 부모 다음 컬럼에 배치된다.
 *
 * O(V+E) — 시드 시나리오 규모(노드 10개 내외)에서는 성능 문제가 없다.
 */
export function layoutDagIntoColumns(nodes: ImpactDagNodeApi[], edges: ImpactDagEdgeApi[]): DagColumn[] {
  if (nodes.length === 0) return [];

  const outgoing = new Map<number, number[]>();
  const inDegree = new Map<number, number>();
  const layer = new Map<number, number>();

  for (const n of nodes) {
    outgoing.set(n.id, []);
    inDegree.set(n.id, 0);
    layer.set(n.id, 0);
  }
  for (const e of edges) {
    outgoing.get(e.from_node_id)?.push(e.to_node_id);
    inDegree.set(e.to_node_id, (inDegree.get(e.to_node_id) ?? 0) + 1);
  }

  // 위상정렬 진행 중 in-degree를 깎아나가므로 원본을 보존한 작업용 사본을 둔다
  const remainingInDegree = new Map(inDegree);
  const queue: number[] = nodes.filter((n) => remainingInDegree.get(n.id) === 0).map((n) => n.id);

  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const next of outgoing.get(current) ?? []) {
      layer.set(next, Math.max(layer.get(next) ?? 0, (layer.get(current) ?? 0) + 1));
      const remaining = (remainingInDegree.get(next) ?? 0) - 1;
      remainingInDegree.set(next, remaining);
      if (remaining === 0) queue.push(next);
    }
  }

  const columnsByLayer = new Map<number, DagColumn["nodes"]>();
  for (const n of nodes) {
    const layerIndex = layer.get(n.id) ?? 0;
    const mapped = {
      id: String(n.id),
      label: n.label,
      isTrigger: inDegree.get(n.id) === 0,
      detail: {
        basis: n.basis,
        uncertainty: n.uncertainty,
        responsibleParty: n.responsible_party,
        affectedTarget: n.affected_target,
        expectedTime: n.expected_time,
      },
    };
    if (!columnsByLayer.has(layerIndex)) columnsByLayer.set(layerIndex, []);
    columnsByLayer.get(layerIndex)!.push(mapped);
  }

  return [...columnsByLayer.keys()]
    .sort((a, b) => a - b)
    .map((layerIndex) => ({ nodes: columnsByLayer.get(layerIndex)! }));
}
