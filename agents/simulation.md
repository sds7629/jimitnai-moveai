# 시뮬레이션 에이전트 (simulation)

## 정체성

숫자를 만들어내는 역할이지만, 숫자의 출처를 숨기지 않는 것이 이 페르소나의 핵심이다. 몬테카를로 엔진을 돌리는 것이 아니라 LLM 한 번의 호출로 기대손실·P90·CVaR·민감도를 산출한다는 것을 알고 있고, 그렇기 때문에 "이 값이 스냅샷에서 그대로 가져온 사실(FACT)인지, DAG 경로로 추론한 값(INFERENCE)인지, LLM이 명시한 가정(ASSUMPTION)인지"를 스키마 레벨에서 강제한다. 근거를 댈 수 없는 숫자는 내보내지 않는다.

## 담당 범위

- **API**: `POST /incidents/{id}/simulate` (비동기 트리거), 결과 조회는 `GET /incidents/{id}/candidates`와 [response-optimization.md](./response-optimization.md)의 `decision-package`를 통해 노출됨
- **DB 테이블**: `simulation_results` (append-only, JSONB로 기대손실/P90/CVaR/민감도/근거 저장)
- **코드 위치(예정)**: `backend/app/services/simulate/simulation.py`, `backend/app/llm/prompts/simulation.py`

## 입력 / 출력

- **입력**: 제약 검증을 통과한 후보 목록, Impact DAG 경로, RAG 검색 결과, 운영 스냅샷 — 이 세 가지를 결합한 단일 LLM 프롬프트 (`ARCHITECTURE.md` §4)
- **출력**: 후보별 기대손실·P90·CVaR·핵심 민감도 변수·신뢰도, FACT/INFERENCE/ASSUMPTION 태깅된 근거 → 대응 최적화 에이전트([response-optimization.md](./response-optimization.md))가 순위화에 사용

## 핵심 설계 원칙

- LLM 예측 파이프라인 순서를 반드시 지킨다 (§4): ① DAG 경로 추출 → ② RAG 검색·병합 → ③ 운영 스냅샷 첨부 → ④ 결합 프롬프트로 LLM 호출 → ⑤ 응답 스키마에 FACT/INFERENCE/ASSUMPTION 강제.
- `simulation_results`는 append-only다 (`operational_snapshots`와 동일한 이유 — baseline 불변성). 재시뮬레이션은 새 레코드를 추가하는 것이지 기존 결과를 고치는 것이 아니다.
- 모든 후보(baseline 포함)를 독립적인 what-if로 각각 계산한다 — 후보 간 비교는 이 단계가 아니라 다음 단계(대응 최적화)의 책임이다. 이 단계에서 순위를 매기지 않는다.
- 신뢰도와 불확실성 범위를 반드시 함께 산출한다 — 단일 기대값만 내보내는 것은 이 페르소나의 책임을 다하지 못한 것이다.

## 의존 관계

- **선행**: 제약 검증 에이전트, 운영 그래프 에이전트(DAG/스냅샷), 지식 검색 에이전트(RAG)
- **후행**: 대응 최적화 에이전트가 이 결과들을 취합해 순위화·조합
- **병렬 가능**: 후보별·시점별·무대응 시뮬레이션은 서로 독립적이므로 병렬 처리 (업무 명세 §7.2 "대응안 평가" 구간)
- **순차 필수**: 제약 검증 → 시뮬레이션 → (결과 취합 후) 대응 조합 최적화 (§7.3)

## 작업 지침 (구현 체크리스트)

1. LLM 응답 Pydantic 스키마에 `fact`/`inference`/`assumption` 필드를 최상위 구조로 강제한다 — 자유 텍스트 근거만 받는 스키마는 불허.
2. `simulation_results.result`(JSONB)에 기대손실/P90/CVaR/민감도 변수/신뢰도를 표준 키로 저장해 이후 대응 최적화·의사결정 패키지 단계가 파싱 가능하게 한다.
3. 후보별 시뮬레이션을 asyncio 등으로 병렬 호출하도록 구성한다 (`POST /incidents/{id}/simulate`가 비동기 트리거인 이유).
4. DAG+RAG+스냅샷을 결합하는 프롬프트 템플릿을 시나리오 유형에 관계없이 공통으로 사용한다 — 시나리오별 프롬프트 분기를 만들지 않는다 (§5의 "이후 파이프라인은 공통 로직" 원칙).
5. 재시뮬레이션 트리거(오케스트레이션 에이전트가 호출)가 들어와도 기존 `simulation_results` 행을 절대 UPDATE하지 않고 새 버전을 추가하도록 리포지토리 레벨에서 강제한다.

## 완료 기준 (Definition of Done)

- [ ] 후보별 결과에 FACT/INFERENCE/ASSUMPTION이 모두 채워짐
- [ ] 동일 사건 재시뮬레이션 시 기존 결과가 아니라 새 버전이 추가됨
- [ ] baseline 포함 모든 후보가 병렬로 계산됨
- [ ] 테스트 최소 3케이스: (1) 정상 시뮬레이션 결과 산출 (2) 재시뮬레이션 시 append-only 유지 (3) LLM 응답이 스키마를 위반할 때(근거 필드 누락) 재시도/오류 처리

## 참고

- `simulation-supply-chain-tool.md` §4.4, §7.1(시뮬레이션 에이전트), §7.2, §7.3
- `ARCHITECTURE.md` §1-3, §2(simulation_results), §4(LLM 예측 파이프라인 전체), §7.1(대응안 생성·제약검증·시뮬레이션 행)
