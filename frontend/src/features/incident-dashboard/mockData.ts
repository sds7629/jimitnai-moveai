import type { IncidentDashboardData } from "./types";

/**
 * "생산라인 파업" 시드 시나리오 목업 데이터.
 * Claude 디자인 와이어프레임(DAG 대시보드.dc.html)에 채워져 있던 값을 그대로 옮겼다.
 * 백엔드 시드 스크립트가 준비되면 GET /incidents/{id}/impact-dag 등 실제 API 응답으로 교체한다
 * (frontend/FRONTEND_ARCHITECTURE.md §6 "시드 데이터가 곧 프론트 개발용 mock" 원칙).
 */
export const strikeScenarioMock: IncidentDashboardData = {
  incident: {
    name: "생산라인 파업",
    progressBadge: "진입 N5ㆍ2일",
    rawTextPlaceholder: "예: 생산라인 A 3시간째 가동 중단, 원인 미확인 (사건 원문 입력)",
  },
  dag: [
    {
      nodes: [
        { id: "port-busan", entityType: "port", label: "부산신항 HPNT", isTrigger: true },
      ],
    },
    {
      nodes: [
        {
          id: "part-semiconductor",
          entityType: "part",
          label: "반도체ㆍ전장",
          delayDays: 1.5,
          costImpact: "996.1억원",
        },
        { id: "part-battery", entityType: "part", label: "배터리셀" },
      ],
    },
    {
      nodes: [
        {
          id: "line-ulsan",
          entityType: "production_line",
          label: "울산 3라인",
          delayDays: 1.5,
        },
        { id: "line-asan", entityType: "production_line", label: "아산 라인" },
      ],
    },
    {
      nodes: [
        {
          id: "transport-pctc",
          entityType: "transport",
          label: "PCTC 해상운송 부산→유럽",
          delayDays: 4.5,
          detail: {
            basis: "선사 스케줄 공지, 항구 혼잡도 지표",
            uncertainty: "medium",
            responsibleParty: "해상운송팀",
            affectedTarget: "PCTC 부산→유럽 항로",
            expectedTime: "2026-08-15T09:00:00Z",
          },
        },
      ],
    },
    {
      nodes: [
        {
          id: "port-bremerhaven",
          entityType: "port",
          label: "브레머하펜 BLG 하역",
          delayDays: 4.4,
          costImpact: "6,600만원",
        },
      ],
    },
    {
      nodes: [
        { id: "dealer-de", entityType: "dealer", label: "독일 딜러권역", delayDays: 4.3, costImpact: "39.4억원" },
        { id: "dealer-gb", entityType: "dealer", label: "영국 딜러권역", delayDays: 4.3, costImpact: "34.5억원" },
        { id: "dealer-benelux", entityType: "dealer", label: "베네룩스 딜러권역", delayDays: 4.3, costImpact: "29.5억원" },
      ],
    },
  ],
  candidates: [
    {
      rank: 1,
      name: "임시 초과근무 편성",
      savingsAmount: "-1,100.0억원",
      remainingLoss: "0원",
      mitigationRatio: 100,
    },
    {
      rank: 2,
      name: "안전재고 사전 당김",
      description: "생산라인 안전재고를 선제 확보해 지연 흡수분 확대",
      savingsAmount: "-535.6억원",
      remainingLoss: "564.6억원",
      mitigationRatio: 49,
      detail: {
        p90: "702.1억원",
        cvar: "745.3억원",
        confidencePercent: 78,
        sensitivityVariables: ["안전재고 소진 속도", "대체 항로 확보 여부"],
        fact: { 현재_재고: "480ea", 시간당_소비: "20ea" },
        inference: { 소진_예상_시각: "24시간 후" },
        assumption: { 안전재고_기준: "200ea" },
      },
    },
    {
      rank: 3,
      name: "PCTC 대체 선복ㆍ스케줄 앞당김",
      description: "해상운송 처리능력을 확대해 적체(운송능력 초과) 지연 해소",
      savingsAmount: "-88.5억원",
      remainingLoss: "1,011.7억원",
      mitigationRatio: 8,
    },
    {
      rank: 4,
      name: "수입부품 긴급 항공 전환",
      description: "반도체ㆍ배터리셀을 항공으로 조달해 부품 버퍼를 확보(라인 정지 방지)",
      savingsAmount: "-0원",
      remainingLoss: "1,100.2억원",
      mitigationRatio: 0,
    },
  ],
  excludedCandidates: [
    { name: "대체 완성차 재고 배정", reason: "✕ 가용 대체 완성차 재고 없음(현재고 0), 실행 불가" },
  ],
  matchedSopCount: 6,
  sops: [
    {
      code: "SOP-LINE-01",
      title: "생산라인 정지 위험 대응",
      owningTeam: "공장 운영팀",
      steps: [
        "결품 예상 부품ㆍ소진 예상시각 확정",
        "긴급 조달 옵션 비교: 항공 전환 / 대체 협력사 / 생산순서 변경",
        "라인 정지 임박 시 생산계획팀에 재배열 요청",
        "결정기한 내 미해결 시 라인 정지 공식 통보 및 상위 보고",
      ],
      reference: "생산 비상대응 매뉴얼 §3.2 ㆍ 부품 안전재고 기준표",
    },
    { code: "SOP-AIR-02", title: "수입부품 긴급 항공 전환 절차", owningTeam: "조달ㆍ물류팀" },
    { code: "SOP-DND-03", title: "D&D(체선ㆍ체화) 발생 최소화", owningTeam: "통관ㆍ계약팀" },
    { code: "SOP-DEALER-04", title: "유럽 딜러 납기 지연 사전 통지", owningTeam: "영업ㆍ계약팀" },
    { code: "SOP-STRIKE-05", title: "노동 파업 비상 대응", owningTeam: "노무ㆍ생산관리팀" },
  ],
};
