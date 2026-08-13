import type { ImpactDag as ImpactDagType } from "../types";
import { DagNode } from "./DagNode";

interface ImpactDagProps {
  dag: ImpactDagType;
}

/**
 * Impact DAG 캔버스.
 *
 * 시드 시나리오 3종(항만 적체/파업/관세)은 모두 "단계(컬럼)별 병렬 노드가 순서대로 이어지는" 형태라
 * 범용 그래프 캔버스(React Flow 등) 대신 좌→우 flexbox 배치로 구현했다 — Claude 디자인
 * 와이어프레임(DAG 대시보드.dc.html)의 방식을 그대로 따른 것.
 * 추후 분기·합류가 복잡해지는 시나리오가 생기면 frontend/DAG_VISUALIZATION.md §2.1에서 검토했던
 * dagre 기반 캔버스로 교체를 재검토한다.
 */
export function ImpactDag({ dag }: ImpactDagProps) {
  return (
    <div className="border-b border-[var(--border)] px-7 py-5">
      <div className="mb-3.5 text-[13px] font-bold text-[var(--text-secondary-strong)]">Impact DAG</div>
      <div className="flex items-center gap-2 overflow-x-auto pb-2.5">
        {dag.map((column, columnIndex) => (
          <div key={columnIndex} className="flex items-center gap-2">
            {columnIndex > 0 && (
              <span aria-hidden className="flex-shrink-0 text-[15px] text-[var(--red-connector)]">
                ┄┄▸
              </span>
            )}
            <div className="flex flex-shrink-0 flex-col gap-2.5">
              {column.nodes.map((node) => (
                <DagNode key={node.id} node={node} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
