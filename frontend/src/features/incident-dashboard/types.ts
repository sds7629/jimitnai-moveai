/**
 * 인시던트 대시보드(DAG + 대응안 랭킹 + SOP + 승인) 데이터 타입.
 *
 * `frontend/DAG_VISUALIZATION.md`, `frontend/DAG_SCREEN_DESIGN_BRIEF.md`의 스키마 초안을
 * Claude 디자인 와이어프레임(DAG 대시보드.dc.html)에서 확정된 필드로 갱신했다.
 * 백엔드 OpenAPI 스키마가 나오면 이 타입은 생성 타입으로 교체될 예정 — 그 전까지의 임시 계약.
 */

/** AI(LLM) 파이프라인 상태. 헤더 우측 뱃지에 표시. */
export type AiStatus = "live" | "cache_fallback" | "degraded";

/**
 * 대응안 랭킹 계산 방식.
 * - individual: 각 후보를 단독으로 적용했을 때의 결과
 * - cumulative: 1→N번 순차 누적 적용했을 때의 결과
 * (frontend/DAG_SCREEN_DESIGN_BRIEF.md §4에서 남긴 계산 의미 미정 이슈 — 백엔드 확정값 확인 필요)
 */
export type RankingMode = "individual" | "cumulative";

/**
 * Impact DAG 노드의 도메인 엔티티 종류.
 * frontend/docs/FEATURE_PHASES.md Phase 2: 실제 백엔드 응답(impact_dag_nodes)에는 이 필드가 없다 —
 * 백엔드가 나중에 추가하면 다시 채워 넣을 수 있도록 optional로만 남겨둔다.
 */
export type DagEntityType =
  | "port"
  | "part"
  | "production_line"
  | "transport"
  | "dealer";

export type EvidenceTag = "FACT" | "INFERENCE" | "ASSUMPTION";

/**
 * 노드 클릭 시 펼쳐지는 근거 상세.
 * backend/app/schemas/impact_dag.py의 ImpactDagNodeRead 필드를 그대로 사용한다 (Phase 2에서
 * FACT/INFERENCE 뱃지·확신도% 같은 와이어프레임 전용 필드를 실제 값으로 교체).
 */
export interface ImpactDagNodeDetail {
  basis: string | null;
  uncertainty: string | null;
  responsibleParty: string | null;
  affectedTarget: string | null;
  /** ISO 문자열. 렌더링 시점에 포맷한다. */
  expectedTime: string | null;
}

export interface ImpactDagNode {
  id: string;
  /** 실제 API에는 아직 없는 필드 — 있으면 라벨을 표시하고, 없으면 표시하지 않는다 */
  entityType?: DagEntityType;
  label: string;
  /** 트리거(루트) 노드는 중립 스타일로 표시하고 지표/점 표시를 하지 않는다 */
  isTrigger?: boolean;
  delayDays?: number;
  /** 이미 포맷된 금액 문자열 (예: "996.1억원"). 통화 단위 포맷은 아직 확정 전 임시 표기. */
  costImpact?: string;
  detail?: ImpactDagNodeDetail;
}

/** DAG는 좌→우로 이어지는 단계(컬럼)의 배열이며, 각 단계에는 병렬 노드가 여러 개일 수 있다 */
export interface DagColumn {
  nodes: ImpactDagNode[];
}

export type ImpactDag = DagColumn[];

/** 대응안 후보 상세(펼쳤을 때 표시할 자리표시자 영역) */
export interface ResponseCandidateDetail {
  /** P90/CVaR 분포 차트 자리표시자 — simulation-supply-chain-tool.md §5.1 */
  distributionPlaceholder: string;
  /** 지금 대응·6시간 후 대응·무대응 비교 자리표시자 */
  baselineComparisonPlaceholder: string;
}

export interface ResponseCandidate {
  rank: number;
  name: string;
  /** 포맷된 절감액 문자열 (예: "-535.6억원") */
  savingsAmount: string;
  description?: string;
  /** 포맷된 잔여손실 문자열 (예: "564.6억원") */
  remainingLoss: string;
  /** 진행바에 표시할 완화율(0~100) */
  mitigationRatio: number;
  detail?: ResponseCandidateDetail;
}

export interface ExcludedCandidate {
  name: string;
  reason: string;
}

export interface MatchedSop {
  code: string;
  title: string;
  owningTeam: string;
  /** steps/reference가 있으면 아코디언으로 펼칠 수 있다 */
  steps?: string[];
  reference?: string;
}

/** 승인 액션 종류 — simulation-supply-chain-tool.md §5.2 승인 분기와 대응 */
export type ApprovalAction = "approve" | "conditional" | "revise" | "reject";

export interface IncidentSummary {
  name: string;
  /** "진입 N5ㆍ2일" 배지 원문 — 정확한 의미 확인 전까지 문자열 그대로 보관 */
  progressBadge: string;
  rawTextPlaceholder: string;
}

export interface IncidentDashboardData {
  incident: IncidentSummary;
  dag: ImpactDag;
  candidates: ResponseCandidate[];
  excludedCandidates: ExcludedCandidate[];
  matchedSopCount: number;
  sops: MatchedSop[];
}
