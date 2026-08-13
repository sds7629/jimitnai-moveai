import type { CausalPathSection } from "../../decision-package/types";

function formatExpectedTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

interface CausalPathListProps {
  section: CausalPathSection;
}

/**
 * 의사결정 근거 Phase 15 — causal_path를 노드 순서 리스트로 렌더링한다.
 * 각 노드는 DagNode(Impact DAG 컴포넌트)와 같은 톤으로 불확실성 뱃지 + 근거/책임 주체/영향
 * 대상/예상 시각을 보여주고, 인접한 두 노드 사이에는 해당 엣지의 basis를 화살표 아래 표시한다
 * (frontend/docs/FEATURE_PHASES.md Phase 15).
 */
export function CausalPathList({ section }: CausalPathListProps) {
  const { nodes, edges } = section;

  if (nodes.length === 0) {
    return <div className="text-[11px] text-[var(--text-secondary)]">영향 전파 경로가 없습니다.</div>;
  }

  const edgeByPair = new Map(edges.map((e) => [`${e.from_node_key}->${e.to_node_key}`, e]));

  return (
    <ol className="flex flex-col gap-0">
      {nodes.map((node, index) => {
        const prevNode = nodes[index - 1];
        const edge = prevNode ? edgeByPair.get(`${prevNode.node_key}->${node.node_key}`) : undefined;

        return (
          <li key={node.node_key}>
            {index > 0 && (
              <div className="flex items-center gap-2 pl-3 py-1 text-[10.5px] text-[var(--text-tertiary)]">
                <span aria-hidden>↓</span>
                {edge?.basis && <span>근거: {edge.basis}</span>}
              </div>
            )}
            <div className="flex gap-3 rounded-md border border-[var(--border)] bg-[var(--panel-bg-2)] p-3">
              <div className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-[var(--red-metric)] text-[10.5px] font-bold text-white">
                {index + 1}
              </div>
              <div className="flex-1">
                <div className="text-[12.5px] font-bold text-[var(--text-primary)]">{node.label}</div>
                {node.uncertainty && (
                  <span className="mt-1 inline-block rounded bg-[var(--blue-chip-bg)] px-1.5 py-0.5 text-[9.5px] font-bold text-[var(--blue)]">
                    불확실성: {node.uncertainty}
                  </span>
                )}
                <div className="mt-1 text-[10.5px] leading-relaxed text-[var(--text-secondary)]">
                  {node.basis && (
                    <>
                      ㆍ근거: {node.basis}
                      <br />
                    </>
                  )}
                  {node.responsible_party && (
                    <>
                      ㆍ책임 주체: {node.responsible_party}
                      <br />
                    </>
                  )}
                  {node.affected_target && (
                    <>
                      ㆍ영향 대상: {node.affected_target}
                      <br />
                    </>
                  )}
                  ㆍ예상 시각: {formatExpectedTime(node.expected_time)}
                </div>
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
