import type { AvoidedLossSection, CostAttributionApi, ExpectedVsActualLossSection } from "../types";
import { formatKrwByScale } from "../../../lib/currency";

/** CandidateSummaryApi에서 정산 관점의 기대손실 숫자만 뽑아낸다. 후보 자체가 없거나
 * 시뮬레이션 결과가 없으면 null(→ formatKrwByScale이 "-"로 표시) */
function expectedLossOf(section: ExpectedVsActualLossSection["expected_loss"], key: "baseline" | "approved_candidate"): number | null {
  const candidate = section[key];
  if (!candidate.available) return null;
  if (!candidate.simulation.available) return null;
  return candidate.simulation.expected_loss ?? null;
}

interface LossSettlementCardProps {
  loss: ExpectedVsActualLossSection;
  avoidedLoss: AvoidedLossSection;
  costAttribution: CostAttributionApi;
}

/**
 * 사후보고서 Phase 23 — sections["7_예상_손실과_실제_손실"] + sections["8_회피한_손실과_추가_발생_비용"] +
 * sections["9_LD_DND_귀책_및_비용_부담_주체"]를 "손익 정산 카드" 하나로 렌더링한다
 * (frontend/docs/FEATURE_PHASES.md Phase 23).
 *
 * 섹션 9(costAttribution)는 PostReportPage가 이미 별도로 GET /incidents/{id}/cost-attribution을
 * 호출해 "비용 귀속" 카드로 breakdown 금액/heuristic_disclaimer를 렌더링하고 있으므로, 이 컴포넌트는
 * 그 값을 다시 그리지 않는다 — 여기서는 아직 화면에 없는 matched_ld_clauses/matched_dnd_clauses
 * 매칭 건수만 보충해 "예상 손실 → 회피 추정액 → 귀책 매칭" 흐름을 완성한다. PostReportPage.tsx에서
 * 이 카드를 "비용 귀속" 카드 바로 다음에 배치해야 아래 안내 문구의 "위" 표현이 맞다.
 */
export function LossSettlementCard({ loss, avoidedLoss, costAttribution }: LossSettlementCardProps) {
  const baselineLoss = expectedLossOf(loss.expected_loss, "baseline");
  const approvedLoss = expectedLossOf(loss.expected_loss, "approved_candidate");
  const { expected_avoided_loss: avoided, additional_cost_incurred: additionalCost } = avoidedLoss;

  return (
    <div className="rounded-[10px] border border-[var(--border)] bg-[var(--panel-bg)] p-4.5">
      <div className="mb-3 text-[13.5px] font-bold text-[var(--text-secondary-strong)]">손익 정산</div>

      <div className="text-[12.5px] text-[var(--text-primary)]">
        예상손실: baseline <span className="font-bold">{formatKrwByScale(baselineLoss)}</span> → 승인후보{" "}
        <span className="font-bold">{formatKrwByScale(approvedLoss)}</span>
      </div>
      <div className="mt-2 rounded-md border border-dashed border-[var(--border-dashed)] px-3 py-2 text-[10.5px] text-[var(--text-secondary)]">
        실제 손실: {loss.actual_status} — {loss.actual_loss.reason}
      </div>

      <div className="mt-3 border-t border-[var(--border)] pt-2.5">
        <div className="mb-1 text-[10.5px] font-bold text-[var(--text-secondary-strong)]">회피 추정액</div>
        {avoided.available ? (
          <>
            <div className="text-[15px] font-bold text-[var(--teal)]">{formatKrwByScale(avoided.amount)}</div>
            <div className="mt-1 text-[10.5px] text-[var(--text-tertiary)]">{avoided.note}</div>
          </>
        ) : (
          <div className="rounded-md border border-dashed border-[var(--border-dashed)] px-3 py-2 text-[10.5px] text-[var(--text-secondary)]">
            {avoided.reason}
          </div>
        )}
      </div>

      <div className="mt-2 rounded-md border border-dashed border-[var(--border-dashed)] px-3 py-2 text-[10.5px] text-[var(--text-secondary)]">
        추가 발생 비용: {additionalCost.reason}
      </div>

      <div className="mt-3 border-t border-[var(--border)] pt-2.5">
        <div className="mb-1 text-[10.5px] font-bold text-[var(--text-secondary-strong)]">귀책 매칭</div>
        <div className="flex flex-wrap gap-1.5">
          <span className="rounded-full border border-[var(--border-mid)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
            LD 조항 매칭 {costAttribution.matched_ld_clauses.length}건
          </span>
          <span className="rounded-full border border-[var(--border-mid)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
            D&D 조항 매칭 {costAttribution.matched_dnd_clauses.length}건
          </span>
        </div>
        <div className="mt-1.5 text-[10.5px] text-[var(--text-tertiary)]">상세 금액 분류는 위 비용 귀속 카드 참고</div>
      </div>
    </div>
  );
}
