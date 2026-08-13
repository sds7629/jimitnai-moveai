import type { ExcludedCandidate, ResponseCandidate } from "../incident-dashboard/types";
import { BASELINE_CANDIDATE_TYPE, type CandidateApi } from "./types";
import { formatKrwToEokwon } from "../../lib/currency";

interface MappedCandidates {
  candidates: ResponseCandidate[];
  excludedCandidates: ExcludedCandidate[];
}

/**
 * 백엔드가 description에 접어 넣은 "[카테고리] ..." 접두어를 파싱하기 위한 정규식.
 * candidate_type은 "baseline"/"단일"/"복합" 셋 중 하나뿐이라(DB CHECK 제약,
 * db/init/002-schema.sql, backend/app/services/response_design.py:60-72) 표시용 이름으로
 * 쓸 수 없다 — 실제 대응안 카테고리(컨테이너 우선반출/긴급운송/대체항 등)는
 * response_design.py:300-307에서 description 앞에 "[카테고리] "로 붙여서 내려온다.
 */
const CATEGORY_PREFIX_RE = /^\[([^\]]+)\]\s*/;

const BASELINE_DISPLAY_NAME = "무대응(기준선)";

/**
 * description의 "[카테고리]" 접두어에서 표시용 이름을 뽑아내고, 뽑아낸 만큼 description에서는
 * 잘라낸다(카드에 이름과 설명을 나란히 보여주므로 중복 표기를 피한다).
 *
 * 접두어가 없거나(예: baseline의 "무대응 - 현재 계획대로...") 대괄호가 비어있거나
 * 닫히지 않은 경우엔 description을 그대로 두고, 이름은 candidate_type을 기반으로 한
 * 안전한 값으로 대체한다.
 */
function deriveDisplayFields(c: CandidateApi): { name: string; description: string } {
  const match = c.description.match(CATEGORY_PREFIX_RE);
  const category = match?.[1]?.trim();

  if (match && category) {
    return {
      name: category,
      description: c.description.slice(match[0].length),
    };
  }

  return {
    name: c.candidate_type === BASELINE_CANDIDATE_TYPE ? BASELINE_DISPLAY_NAME : c.candidate_type,
    description: c.description,
  };
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
      id: c.id,
      name: deriveDisplayFields(c).name,
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
    const { name, description } = deriveDisplayFields(c);

    return {
      rank: index + 1,
      name,
      description,
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
