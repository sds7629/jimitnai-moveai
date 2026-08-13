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
    { id: 1, name: "대체 완성차 재고 배정", reason: "✕ 가용 대체 완성차 재고 없음(현재고 0), 실행 불가" },
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
    {
      code: "SOP-AIR-02",
      title: "수입부품 긴급 항공 전환 절차",
      owningTeam: "조달ㆍ물류팀",
      steps: [
        "결품 위험 부품(반도체ㆍ전장, 배터리셀) 재고 소진 예상시각과 필요량 확정",
        "항공 포워더 3개사 이상에 가용 스케줄ㆍ운임 견적 동시 요청",
        "항공 전환 추가 비용과 라인 정지 손실액을 비교해 전환 여부 최종 승인 요청",
        "승인 시 통관ㆍ계약팀에 긴급 통관 사전 등록 요청 및 도착 예정시각 공유",
        "전환 완료 후 해상운송 예약분 취소ㆍ환불 처리 및 결과 보고",
      ],
      reference: "물류 비상대응 매뉴얼 §4.1 ㆍ 항공 포워더 비상연락망",
    },
    {
      code: "SOP-DND-03",
      title: "D&D(체선ㆍ체화) 발생 최소화",
      owningTeam: "통관ㆍ계약팀",
      steps: [
        "선사별 무료 반출기간(Free Time) 만료 예정 컨테이너 목록 확보",
        "반출 지연 원인(통관ㆍ서류ㆍ야드 혼잡) 파악 및 처리 우선순위 재정렬",
        "선사에 Free Time 연장 협상 요청, 불가 시 D&D 비용 견적 사전 확보",
        "우선 반출 대상 컨테이너의 하차ㆍ운송 일정을 물류팀과 조율",
        "발생한 D&D 비용을 정산해 사후보고서에 반영",
      ],
      reference: "통관 실무 매뉴얼 §5.3 ㆍ 선사별 Free Time 기준표",
    },
    {
      code: "SOP-DEALER-04",
      title: "유럽 딜러 납기 지연 사전 통지",
      owningTeam: "영업ㆍ계약팀",
      steps: [
        "권역별(독일ㆍ영국ㆍ베네룩스) 예상 지연일수와 영향 차종ㆍ물량 확정",
        "딜러사에 지연 사전 통지문 발송(예상 지연일수ㆍ대안 포함)",
        "주요 거래선(대형 딜러) 대상 개별 전화ㆍ화상 통화로 보완 설명",
        "계약상 지체상금(penalty) 조항 검토 및 법무팀 자문 요청",
        "딜러 피드백을 수집해 상위 보고 및 후속 대응 여부 결정",
      ],
      reference: "해외영업 대응 가이드 §2.4 ㆍ 딜러 계약서 지체상금 조항",
    },
    {
      code: "SOP-STRIKE-05",
      title: "노동 파업 비상 대응",
      owningTeam: "노무ㆍ생산관리팀",
      steps: [
        "파업 규모ㆍ참여 인원ㆍ예상 지속기간을 노조 채널로 확인",
        "필수 인력(안전ㆍ설비 유지) 확보 여부 점검 및 대체 인력 배치 검토",
        "생산계획팀과 협의해 비파업 라인으로 생산 우선순위 재배정",
        "노무팀 협상 창구 단일화 및 대내외 공식 입장문 준비",
        "타결 또는 장기화 여부에 따라 물량 재계획 및 상위 보고",
      ],
      reference: "노무 리스크 대응 매뉴얼 §1.2 ㆍ 비상 인력 운용 기준",
    },
    {
      code: "SOP-CUSTOMS-06",
      title: "관세ㆍ통관 규정 변경 대응",
      owningTeam: "통관담당팀",
      steps: [
        "변경된 관세ㆍ통관 규정(품목분류ㆍ원산지ㆍ관세율)의 적용 시점과 대상 품목 확인",
        "현재 운송ㆍ통관 진행 중인 화물 중 신규 규정 적용 대상 여부 전수 조사",
        "관세사ㆍ법무팀과 협의해 품목분류 재검토 및 원산지증명 등 서류 재정비",
        "규정 변경으로 인한 추가 관세ㆍ지연 비용을 산정해 재무팀에 통보",
        "관할 세관에 사전 질의ㆍ협의를 진행하고 결과를 관련 부서에 공유",
      ],
      reference: "통관 규정 변경 대응 가이드 §6.1 ㆍ 관세청 품목분류 사전심사 안내",
    },
  ],
};
