import { useState } from "react";
import type { ImpactDagNode } from "../types";

/** 도메인 엔티티 타입 → 노드 상단에 표시할 한국어 라벨 */
const ENTITY_TYPE_LABEL: Record<ImpactDagNode["entityType"], string> = {
  port: "항만",
  part: "부품",
  production_line: "생산라인",
  transport: "운송",
  dealer: "딜러",
};

interface DagNodeProps {
  node: ImpactDagNode;
}

/**
 * Impact DAG의 노드 하나.
 * - 트리거(루트) 노드는 중립 테두리, 지표·점 표시 없음
 * - 영향 노드는 빨간 테두리. 지연일수/비용 지표가 있으면 우상단에 점(dot)과 지표 텍스트를 표시
 * - 근거 상세(detail)가 있으면 클릭으로 펼치고 접을 수 있다 (FACT/INFERENCE/ASSUMPTION 뱃지 포함)
 */
export function DagNode({ node }: DagNodeProps) {
  const [detailOpen, setDetailOpen] = useState(true);
  const hasMetric = node.delayDays !== undefined || node.costImpact !== undefined;
  const borderColor = node.isTrigger ? "border-[var(--border-strong)]" : "border-[var(--red-border)]";

  const metricText = [
    node.delayDays !== undefined ? `+${node.delayDays}일` : null,
    node.costImpact ?? null,
  ]
    .filter(Boolean)
    .join("ㆍ");

  return (
    <div className="flex flex-col gap-2 min-w-[112px] flex-shrink-0">
      <div
        onClick={node.detail ? () => setDetailOpen((open) => !open) : undefined}
        className={`relative flex flex-col gap-0.5 rounded-lg border-[1.5px] ${borderColor} bg-[var(--node-bg)] px-3.5 py-2.5 ${
          node.detail ? "cursor-pointer" : ""
        }`}
      >
        {!node.isTrigger && hasMetric && (
          <span
            aria-hidden
            className="absolute -top-1 -right-1 h-1.5 w-1.5 rounded-full bg-[var(--red)] shadow-[0_0_0_2px_var(--bg-page)]"
          />
        )}
        <div className="text-[9.5px] text-[var(--text-tertiary)]">{ENTITY_TYPE_LABEL[node.entityType]}</div>
        <div className="text-[13.5px] font-bold text-[var(--text-primary)]">{node.label}</div>
        {metricText && (
          <div className="text-[10.5px] text-[var(--red-metric)]">
            {metricText}
            {node.detail && <span>ㆍ{detailOpen ? "▾" : "▸"} 클릭 상세</span>}
          </div>
        )}
      </div>

      {node.detail && detailOpen && (
        <div className="w-[210px] rounded-md border border-dashed border-[var(--border-dashed)] bg-[var(--panel-bg-2)] px-3 py-2.5 text-[10.5px] leading-relaxed text-[var(--text-secondary)]">
          <div className="mb-1.5 flex gap-1.5">
            {node.detail.evidenceTags.map((tag) => (
              <span
                key={tag}
                className={`rounded px-1.5 py-0.5 text-[9.5px] font-bold ${
                  tag === "FACT"
                    ? "bg-[var(--blue-chip-bg)] text-[var(--blue)]"
                    : "bg-[var(--red-chip-bg)] text-[var(--red)]"
                }`}
              >
                {tag}
              </span>
            ))}
          </div>
          <div>
            ㆍ확신도 {node.detail.confidencePercent}%
            <br />ㆍ{node.detail.evidenceText}
            <br />ㆍ근거 소스 링크 →
          </div>
        </div>
      )}
    </div>
  );
}
