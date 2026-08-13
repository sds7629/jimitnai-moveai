/**
 * GET /incidents/{id}/decision-package 응답 타입.
 * backend/app/schemas/decision_package.py + app/services/response_optimization.py의
 * build_decision_package 문서화 주석을 기준으로 옮겼다 (Phase 6).
 *
 * `package`는 백엔드도 의도적으로 세부 Pydantic 모델 대신 dict[str, Any]로 유지한다(10개 섹션의
 * 형태가 app/services/response_optimization.py 한 곳에서만 문서화·강제됨) — 프론트도 같은 방침으로
 * 느슨하게 타입을 잡고, 렌더링은 섹션 단위로 일반화한다.
 */
export interface DecisionPackageApi {
  id: number;
  incident_id: number;
  package: Record<string, unknown>;
  recommended_deadline: string | null;
  created_at: string;
}

/** package의 10개 필수 섹션 + 순위/면책 키를 화면에 표시할 순서와 한글 라벨 */
export const DECISION_PACKAGE_SECTIONS: { key: string; label: string }[] = [
  { key: "expected_loss_p90_cvar", label: "기대손실·P90·CVaR" },
  { key: "now_vs_6h_vs_no_action", label: "지금 대응 vs 6시간 후 대응 vs 무대응" },
  { key: "causal_path", label: "영향 전파 경로" },
  { key: "data_and_documents_used", label: "사용한 데이터·문서" },
  { key: "fact_inference_assumption", label: "FACT·INFERENCE·ASSUMPTION" },
  { key: "freshness_and_coverage", label: "데이터 최신성·커버리지" },
  { key: "key_sensitivity_variables", label: "핵심 민감도 변수" },
  { key: "feasibility_and_exclusion", label: "실행 가능성·제외 사유" },
  { key: "confidence_and_uncertainty", label: "신뢰도·불확실성" },
  { key: "ranked_candidates", label: "대응 조합 순위" },
];

/**
 * Phase 13 전용 타입 — package["expected_loss_p90_cvar"], package["confidence_and_uncertainty"]의
 * 실제 형태(backend/app/services/response_optimization.py build_decision_package 확인).
 * 둘 다 candidate id(string) 키로 묶여 있어서 후보별 표 하나로 합칠 수 있다.
 */
export interface ExpectedLossP90CvarEntry {
  candidate_type: string;
  description: string;
  expected_loss: number | null;
  p90: number | null;
  cvar: number | null;
}
export type ExpectedLossP90CvarSection = Record<string, ExpectedLossP90CvarEntry>;

export interface UncertaintyRangeApi {
  expected_loss: number | null;
  p90: number | null;
  cvar: number | null;
  p90_minus_expected_loss: number | null;
  cvar_minus_p90: number | null;
}
export interface ConfidenceAndUncertaintyEntry {
  confidence: number | null;
  uncertainty_range: UncertaintyRangeApi;
}
export type ConfidenceAndUncertaintySection = Record<string, ConfidenceAndUncertaintyEntry>;

/**
 * Phase 14 전용 타입 — package["now_vs_6h_vs_no_action"]의 실제 형태
 * (backend/app/services/response_optimization.py _pair_summary 확인). 세 슬롯 중 해당하는
 * 후보가 없으면 null.
 */
export interface PairSummaryApi {
  candidate_id: number;
  candidate_type: string;
  description: string;
  start_time_variant: string | null;
  expected_loss: number | null;
  p90: number | null;
  cvar: number | null;
}
export interface NowVs6hVsNoActionSection {
  no_action: PairSummaryApi | null;
  now: PairSummaryApi | null;
  plus_6h: PairSummaryApi | null;
}

/**
 * Phase 15 전용 타입 — package["causal_path"]의 실제 형태
 * (backend/app/services/response_optimization.py _causal_path 확인). 최신 스냅샷의
 * Impact DAG 노드를 순서 그대로 담고, 엣지는 노드 사이 인과 관계를 node_key로 연결한다.
 */
export interface CausalPathNodeApi {
  node_key: string;
  label: string;
  affected_target: string | null;
  expected_time: string | null;
  basis: string | null;
  responsible_party: string | null;
  uncertainty: string | null;
}
export interface CausalPathEdgeApi {
  from_node_key: string;
  to_node_key: string;
  basis: string | null;
}
export interface CausalPathSection {
  nodes: CausalPathNodeApi[];
  edges: CausalPathEdgeApi[];
}

/**
 * Phase 16 전용 타입 — package["data_and_documents_used"] +
 * package["fact_inference_assumption"] + package["freshness_and_coverage"]의 실제 형태
 * (backend/app/services/response_optimization.py build_decision_package 4~6번 항목 확인).
 * fact/inference/assumption은 LLM이 만든 자유 형식 JSONB(dict[str, Any])라 프론트도 같은
 * 방침으로 느슨하게 타입을 잡는다.
 */
export interface DataAndDocumentsUsedSection {
  operational_assumptions: string[];
  data_version: string;
  scenario_version: string;
  reference_document_ids_by_candidate: Record<string, string[]>;
}

export interface FactInferenceAssumptionEntry {
  fact: Record<string, unknown>;
  inference: Record<string, unknown>;
  assumption: Record<string, unknown>;
}
export type FactInferenceAssumptionSection = Record<string, FactInferenceAssumptionEntry>;

export interface FreshnessAndCoverageSection {
  quality_mode: string;
  freshness_seconds: number | null;
  coverage_ratio: number | null;
}
