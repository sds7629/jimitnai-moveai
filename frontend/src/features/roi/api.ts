import { apiGet } from "../../lib/apiClient";
import type { RoiApiResponse } from "./types";

/** GET /reports/roi — 사건 독립적 전역 엔드포인트, 파라미터 없이 기본값(§10 예시값)으로 계산 */
export function getRoi(): Promise<RoiApiResponse> {
  return apiGet<RoiApiResponse>("/reports/roi");
}
