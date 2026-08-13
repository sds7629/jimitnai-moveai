# Impact DAG 시각화 설계 노트

`FRONTEND_ARCHITECTURE.md`에서 DAG 시각화 라이브러리로 **React Flow**를 확정했지만, 실제 구현에 필요한
레이아웃 방식·데이터 스키마·시각적 인코딩은 아직 비어 있다. 이 문서는 그 빈 부분을 채우기 위한 설계
노트이며, `ARCHITECTURE.md` §7.3의 "DAG 시각화는 별도 트랙" 원칙에 따라 백엔드 API가 준비되기 전에도
독립적으로 착수할 수 있도록 프론트 쪽에서 먼저 제안하는 초안이다.

## 1. 확정된 전제 (다른 문서에서 이미 정해진 것)

- 렌더링 라이브러리: **React Flow** (`@xyflow/react`)
- 화면 경로: `/incidents/:id/dag`
- 데이터 소스: `GET /incidents/{id}/impact-dag`, 개발 중에는 MSW 고정 fixture(적체/파업/관세 3종)
- 인터랙션: 노드 클릭 시 근거·불확실성을 사이드 패널에 표시
- 실시간 갱신: SSE `dag_updated` 이벤트 → TanStack Query invalidate → refetch (폴링 없음)
- 도메인 요구 필드(노드·엣지 공통, `simulation-supply-chain-tool.md` §4.1): 영향 대상, 예상 발생시각,
  계산 근거, 책임 주체, 불확실성
- **`simulation-supply-chain-tool.md` §9**: "Impact DAG **위에는** 지연 발생 구간과 책임 주체를 연결한
  귀책 지도를 표시한다" → 귀책 지도는 별도 화면이 아니라 **같은 DAG 컴포넌트의 오버레이/모드**로 구현해야
  한다. `FRONTEND_ARCHITECTURE.md` §3 라우팅 표에는 별도 경로로 잡혀 있지 않으므로 누락하기 쉽다.

## 2. 지금 결정해야 하는 것

### 2.1 레이아웃 엔진

React Flow 자체는 auto-layout을 제공하지 않는다. 노드 좌표를 별도 알고리즘으로 계산해야 한다.

| 후보 | 특징 |
|---|---|
| `dagre` | 계층형(Sugiyama) 레이아웃. 가볍고 단순한 체인/약한 분기 그래프에 적합 |
| `elkjs` | 엣지 라우팅·교차 최소화가 더 정교하지만 무겁고 설정이 복잡 |

도메인 스펙의 기본 흐름은 선형 체인(항만 적체 → … → 딜러 납기 위반)이지만, "그래프"가 아니라 "DAG"라고
부르는 이유가 있다 — 복합 시나리오(예: 파업 + 관세 동시 발생)에서 여러 원인이 한 노드로 합류(fan-in)하거나,
하나의 영향이 여러 부품·고객으로 분기(fan-out)할 수 있다.

**권장**: `dagre`로 시작하고, 분기·교차가 실제로 복잡해지는 시점에 `elkjs`로 교체 검토.

### 2.2 노드/엣지 데이터 스키마 (프론트 초안 제안)

`ARCHITECTURE.md`에는 `impact_dag_nodes` / `impact_dag_edges` 테이블 존재만 명시되어 있고 컬럼 스펙이
없다. DAG를 프론트가 먼저 착수하려면 이 스키마를 프론트가 초안으로 제안하고, 이후 백엔드와
contract-first로 맞추는 순서가 맞다.

```ts
type ImpactDagNode = {
  id: string;
  label: string;                 // 영향 대상 (예: "부품 재고 소진")
  nodeType: "trigger" | "impact" | "outcome"; // 스타일 분기용
  expectedAt?: string;           // ISO 시각
  expectedAtRange?: [string, string]; // 불확실하면 range로 대체
  evidenceType: "FACT" | "INFERENCE" | "ASSUMPTION";
  evidence: string;              // 계산 근거 설명
  responsibleParty: string;
  uncertainty: "low" | "medium" | "high";
  costAttribution?: {            // §9 귀책 지도용, 없을 수도 있음
    ldOwner?: string;
    ddOwner?: string;
  };
};

type ImpactDagEdge = {
  id: string;
  source: string;
  target: string;
  label?: string;                 // 예: "6시간 내 소진"
  evidenceType: "FACT" | "INFERENCE" | "ASSUMPTION";
  uncertainty: "low" | "medium" | "high";
};
```

`FACT/INFERENCE/ASSUMPTION`은 원래 decision-package 응답 스키마(`ARCHITECTURE.md` §4)에 강제된
필드인데, DAG 노드의 "계산 근거"도 같은 태그를 재사용하는 것이 일관적이다 — 이 부분은 백엔드와 확인
필요.

### 2.3 시각적 인코딩

"표시해야 한다"까지만 정해져 있고 "어떻게"는 비어 있다.

- 노드 테두리 색/두께 = `uncertainty` (low = 실선 얇게, high = 경고색 두껍게 또는 점선)
- 엣지 스타일 = `evidenceType` (FACT = 실선, INFERENCE = 파선, ASSUMPTION = 점선 + 반투명)
- 노드 내부에 `evidenceType` 텍스트 뱃지 병기 (색상만으로 구분하면 접근성 문제)

### 2.4 귀책 지도(§9) 오버레이

같은 DAG 위에서 "기본 보기"와 "귀책 보기"를 토글하는 구조를 권장한다 (별도 페이지로 중복 구현하지
않음). 귀책 보기에서는 노드/엣지에 LD/D&D 책임 주체 라벨을 얹고 주체별로 색상 그룹핑한다.

### 2.5 SSE 갱신 시 리레이아웃 흔들림

`dag_updated`로 전체 스냅샷을 다시 받으면 `dagre`가 처음부터 재계산한다. 노드 집합이 그대로면 좌표는
결정적으로 동일하지만, 새 노드가 추가되면 하위 노드 전체 좌표가 밀린다. React Flow는 노드 position
변경에 CSS transition을 걸 수 있으므로, 급격한 점프 대신 애니메이션으로 완충하는 것을 기본으로 한다 —
매 갱신마다 그래프가 재배치되어 사용자가 흐름을 못 따라가는 문제를 방지한다.

### 2.6 대응안 비교와의 경계

"지금 대응·6시간 후 대응·무대응 비교"(`simulation-supply-chain-tool.md` §4.4/§5.1)는 명세상
`/incidents/:id/candidates`의 카드/차트(Recharts) 영역이며, DAG 위에 얹으라는 요구는 없다. DAG에
what-if 오버레이까지 넣는 것은 스코프 확장이므로 지금은 하지 않는다. 필요성이 확인되면 이 항목만
재검토한다.

## 3. 권장 스택

`@xyflow/react` + `dagre`(레이아웃) + 커스텀 노드/엣지 타입 2종(기본/귀책 모드 공용, prop으로 모드
스위치) + 사이드 패널(노드 클릭 시 근거·불확실성) + MSW로 3개 시드 시나리오 DAG JSON을 고정 fixture로
사용.

## 4. 다음 단계

1. 위 `ImpactDagNode` / `ImpactDagEdge` 스키마 초안을 백엔드 세션과 맞춰 확정 (contract-first 원칙)
2. 3개 시나리오(적체/파업/관세) 중 하나로 고정 mock JSON 먼저 작성
3. `dagre` 레이아웃 + 기본 노드 렌더링부터 구현 착수

## 5. 이번 스코프에서 제외

- DAG 위 what-if(대응안별) 오버레이 — §2.6 참조
- 대규모 그래프 대상 가상화/성능 최적화 — 시드 시나리오 규모(노드 10개 내외)에서는 불필요
