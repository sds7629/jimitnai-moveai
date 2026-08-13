/**
 * GET /incidents/{id}/post-report, GET /incidents/{id}/cost-attribution 응답 타입.
 * backend/app/schemas/post_report.py를 그대로 옮겼다 (Phase 11).
 *
 * 이 시스템엔 실적 확정값을 입력받는 API가 없어서 report_status는 항상 "잠정",
 * actual_status는 항상 "미확정"이다(backend/app/services/post_report.py 모듈 docstring) —
 * 화면에서 이 제약을 숨기지 않고 그대로 노출해야 한다.
 */
export interface PostReportApi {
  incident_id: number;
  report_status: string;
  actual_status: string;
  scope_limitation_note: string;
  generated_at: string;
  sections: Record<string, unknown>;
}

/** simulation-supply-chain-tool.md §8.2 12개 섹션 — build_post_report의 실제 키 순서 그대로 */
export const POST_REPORT_SECTIONS: { key: string; label: string }[] = [
  { key: "1_사건_개요와_발생시점", label: "1. 사건 개요와 발생시점" },
  { key: "2_최초_예상과_실제_진행_과정", label: "2. 최초 예상과 실제 진행 과정" },
  { key: "3_주요_동적_변수의_변화", label: "3. 주요 동적 변수의 변화" },
  { key: "4_검토한_대응안과_제외_사유", label: "4. 검토한 대응안과 제외 사유" },
  { key: "5_최종_결정과_승인자", label: "5. 최종 결정과 승인자" },
  { key: "6_SOP_발송_수신_수락_실행_이력", label: "6. SOP 발송·수신·수락·실행 이력" },
  { key: "7_예상_손실과_실제_손실", label: "7. 예상 손실과 실제 손실" },
  { key: "8_회피한_손실과_추가_발생_비용", label: "8. 회피한 손실과 추가 발생 비용" },
  { key: "9_LD_DND_귀책_및_비용_부담_주체", label: "9. LD·D&D 귀책 및 비용 부담 주체" },
  { key: "10_시뮬레이션_오차와_가정의_영향", label: "10. 시뮬레이션 오차와 가정의 영향" },
  {
    key: "11_자원_확보_실패_실행_편차와_에스컬레이션_이력",
    label: "11. 자원 확보 실패·실행 편차와 에스컬레이션 이력",
  },
  { key: "12_향후_SOP_모델_데이터_개선사항", label: "12. 향후 SOP·모델·데이터 개선사항" },
];

/**
 * GET /incidents/{id}/cost-attribution 응답.
 * breakdown은 항상 이 3개 키를 갖는다: "직접_손익_효과" / "고객_회피비용" / "분쟁_협상_가능_금액"
 * (backend/app/services/cost_attribution.py DIRECT_PL_KEY 등). is_heuristic이 true인 한
 * heuristic_disclaimer("법무 판단 대체 아님")를 화면에서 생략하면 안 된다.
 */
export interface CostAttributionApi {
  incident_id: number;
  is_heuristic: boolean;
  rag_unavailable: boolean;
  heuristic_disclaimer: string;
  avoided_loss_basis: Record<string, unknown>;
  matched_ld_clauses: Record<string, unknown>[];
  matched_dnd_clauses: Record<string, unknown>[];
  breakdown: Record<string, number | null>;
  classification_note: string;
}

export const COST_ATTRIBUTION_LABELS: { key: string; label: string }[] = [
  { key: "직접_손익_효과", label: "직접 손익 효과" },
  { key: "고객_회피비용", label: "고객 회피비용" },
  { key: "분쟁_협상_가능_금액", label: "분쟁·협상 가능 금액" },
];
