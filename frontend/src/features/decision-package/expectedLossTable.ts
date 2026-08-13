import { formatKrwToEokwon } from "../../lib/currency";
import type { ConfidenceAndUncertaintySection, ExpectedLossP90CvarSection } from "./types";

export interface ExpectedLossTableRow {
  candidateId: string;
  candidateType: string;
  description: string;
  expectedLoss: string;
  p90: string;
  cvar: string;
  confidencePercent: number | null;
  p90MinusExpectedLoss: string;
  cvarMinusP90: string;
}

/** 원(KRW) → "###.#억원", null/undefined면 "-" — 부호 있는 값(음수 허용)도 그대로 처리 */
function formatSigned(value: number | null | undefined): string {
  if (value == null) return "-";
  return formatKrwToEokwon(value);
}

/**
 * package["expected_loss_p90_cvar"] + package["confidence_and_uncertainty"]를
 * candidate id 기준으로 합쳐 표 행으로 변환한다 (Phase 13).
 * 기준 목록은 expected_loss_p90_cvar이다 — confidence_and_uncertainty에 짝이 없는 후보는
 * (이론상 발생하지 않지만 방어적으로) null 값으로 채운다.
 */
export function buildExpectedLossTable(
  expectedLossSection: ExpectedLossP90CvarSection,
  confidenceSection: ConfidenceAndUncertaintySection,
): ExpectedLossTableRow[] {
  return Object.entries(expectedLossSection).map(([candidateId, entry]) => {
    const confidenceEntry = confidenceSection[candidateId];
    const range = confidenceEntry?.uncertainty_range;

    return {
      candidateId,
      candidateType: entry.candidate_type,
      description: entry.description,
      expectedLoss: formatSigned(entry.expected_loss),
      p90: formatSigned(entry.p90),
      cvar: formatSigned(entry.cvar),
      confidencePercent: confidenceEntry?.confidence != null ? Math.round(confidenceEntry.confidence * 100) : null,
      p90MinusExpectedLoss: formatSigned(range?.p90_minus_expected_loss ?? null),
      cvarMinusP90: formatSigned(range?.cvar_minus_p90 ?? null),
    };
  });
}
