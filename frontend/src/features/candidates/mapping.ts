import type { ExcludedCandidate, ResponseCandidate } from "../incident-dashboard/types";
import { BASELINE_CANDIDATE_TYPE, type CandidateApi } from "./types";

/** 원(KRW) → "###.#억원" 문자열. null이면 "-" */
function formatKrwToEokwon(value: number | null): string {
  if (value === null) return "-";
  return `${(value / 100_000_000).toFixed(1)}억원`;
}

interface MappedCandidates {
  candidates: ResponseCandidate[];
  excludedCandidates: ExcludedCandidate[];
}

/**
 * 실제 GET /candidates 응답을 대시보드 표시용으로 변환한다.
 *
 * - baseline 후보 자신은 "무대응 기준선"이라 랭킹 목록에 넣지 않고, 다른 후보의 절감액을
 *   계산하는 기준으로만 쓴다.
 * - latest_simulation이 아직 없는 후보(POST /simulate 실행 전)는 기대손실이 없어 정렬할 수
 *   없으므로 랭킹에서 제외한다 — 제외된 대응안(불가능 판정)과는 다른 개념이라 excludedCandidates에도
 *   넣지 않는다.
 * - validation_status가 '불가능'인 후보만 excludedCandidates로 분류한다.
 */
export function mapCandidatesToDashboard(candidates: CandidateApi[]): MappedCandidates {
  const baseline = candidates.find((c) => c.candidate_type === BASELINE_CANDIDATE_TYPE);
  const baselineLoss = baseline?.latest_simulation?.expected_loss ?? null;

  const excludedCandidates: ExcludedCandidate[] = candidates
    .filter((c) => c.validation_status === "불가능")
    .map((c) => ({
      name: c.candidate_type,
      reason: `${c.exclusion_category ?? "사유 미상"}: ${c.exclusion_detail ?? "사유 미상"}`,
    }));

  const ranked = candidates
    .filter(
      (c) =>
        c.candidate_type !== BASELINE_CANDIDATE_TYPE &&
        c.validation_status !== "불가능" &&
        c.latest_simulation !== null,
    )
    .sort((a, b) => a.latest_simulation!.expected_loss! - b.latest_simulation!.expected_loss!);

  const mapped: ResponseCandidate[] = ranked.map((c, index) => {
    const sim = c.latest_simulation!;
    const expectedLoss = sim.expected_loss;
    const savings = baselineLoss !== null && expectedLoss !== null ? baselineLoss - expectedLoss : null;

    return {
      rank: index + 1,
      name: c.candidate_type,
      description: c.description,
      remainingLoss: formatKrwToEokwon(expectedLoss),
      savingsAmount: savings === null ? "-" : `-${formatKrwToEokwon(Math.abs(savings))}`,
      mitigationRatio:
        savings !== null && baselineLoss !== null && baselineLoss > 0
          ? Math.min(100, Math.max(0, Math.round((savings / baselineLoss) * 100)))
          : 0,
      detail: {
        p90: formatKrwToEokwon(sim.p90),
        cvar: formatKrwToEokwon(sim.cvar),
        confidencePercent: sim.confidence !== null ? Math.round(sim.confidence * 100) : null,
        sensitivityVariables: sim.sensitivity_variables,
        fact: sim.fact,
        inference: sim.inference,
        assumption: sim.assumption,
      },
    };
  });

  return { candidates: mapped, excludedCandidates };
}
