import { useState } from "react";
import type { ImpactDagNode } from "../types";

/** 도메인 엔티티 타입 → 노드 상단에 표시할 한국어 라벨. 실제 API에는 아직 없는 필드라 없으면 라벨 자체를 생략한다 */
const ENTITY_TYPE_LABEL: Record<NonNullable<ImpactDagNode["entityType"]>, string> = {
  port: "항만",
  part: "부품",
  production_line: "생산라인",
  transport: "운송",
  dealer: "딜러",
};

function formatExpectedTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

interface DagNodeProps {
  node: ImpactDagNode;
}

/**
 * Impact DAG의 노드 하나.
 * - 트리거(루트) 노드는 중립 테두리, 지표·점 표시 없음
 * - 영향 노드는 빨간 테두리. 지연일수/비용 지표가 있으면(현재 실제 API엔 없음) 우상단에 점(dot)과
 *   지표 텍스트를 표시
 * - 근거 상세(detail)가 있으면 클릭으로 펼치고 접을 수 있다 — basis/uncertainty/responsible_party 등
 *   실제 값을 그대로 보여준다 (frontend/docs/FEATURE_PHASES.md Phase 2)
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
        {node.entityType && (
          <div className="text-[9.5px] text-[var(--text-tertiary)]">{ENTITY_TYPE_LABEL[node.entityType]}</div>
        )}
        <div className="text-[13.5px] font-bold text-[var(--text-primary)]">{node.label}</div>
        {(metricText || node.detail) && (
          <div className="text-[10.5px] text-[var(--red-metric)]">
            {metricText}
            {node.detail && (
              <span>
                {metricText && "ㆍ"}
                <span
                  aria-hidden
                  className={`inline-block transition-transform duration-200 ${detailOpen ? "rotate-90" : "rotate-0"}`}
                >
                  ▸
                </span>{" "}
                클릭 상세
              </span>
            )}
          </div>
        )}
      </div>

      {node.detail && (
        <div
          data-testid="dag-node-detail-wrapper"
          className={`grid transition-all duration-200 ${detailOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}
        >
          <div className="overflow-hidden">
            <div className="w-[210px] rounded-md border border-dashed border-[var(--border-dashed)] bg-[var(--panel-bg-2)] px-3 py-2.5 text-[10.5px] leading-relaxed text-[var(--text-secondary)]">
              {node.detail.uncertainty && (
                <div className="mb-1.5">
                  <span className="rounded bg-[var(--blue-chip-bg)] px-1.5 py-0.5 text-[9.5px] font-bold text-[var(--blue)]">
                    불확실성: {node.detail.uncertainty}
                  </span>
                </div>
              )}
              <div>
                {node.detail.basis && (
                  <>
                    ㆍ근거: {node.detail.basis}
                    <br />
                  </>
                )}
                {node.detail.responsibleParty && (
                  <>
                    ㆍ책임 주체: {node.detail.responsibleParty}
                    <br />
                  </>
                )}
                {node.detail.affectedTarget && (
                  <>
                    ㆍ영향 대상: {node.detail.affectedTarget}
                    <br />
                  </>
                )}
                ㆍ예상 시각: {formatExpectedTime(node.detail.expectedTime)}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
