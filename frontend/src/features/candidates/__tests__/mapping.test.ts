import { describe, expect, it } from "vitest";
import { mapCandidatesToDashboard } from "../mapping";
import type { CandidateApi, SimulationResultApi } from "../types";

function sim(overrides: Partial<SimulationResultApi> = {}): SimulationResultApi {
  return {
    id: 1,
    candidate_id: 1,
    incident_id: 1,
    expected_loss: 100_000_000,
    p90: 150_000_000,
    cvar: 180_000_000,
    sensitivity_variables: [],
    confidence: 0.8,
    fact: {},
    inference: {},
    assumption: {},
    data_version: "v1",
    scenario_version: "s1",
    created_at: "2026-08-13T00:00:00Z",
    ...overrides,
  };
}

function candidate(overrides: Partial<CandidateApi> = {}): CandidateApi {
  return {
    id: 1,
    incident_id: 1,
    snapshot_id: 1,
    // candidate_type은 DB CHECK 제약(db/init/002-schema.sql)상 "baseline"/"단일"/"복합" 셋 뿐이다 —
    // 실제 카테고리(예: 안전재고 사전 당김)는 description의 "[카테고리] ..." 접두어로 내려온다
    // (backend/app/services/response_design.py:300-307).
    candidate_type: "단일",
    description: "[안전재고 사전 당김] 설명",
    reference_document_ids: [],
    preconditions: [],
    start_time_variant: null,
    validation_status: "가능",
    exclusion_category: null,
    exclusion_detail: null,
    created_at: "2026-08-13T00:00:00Z",
    updated_at: "2026-08-13T00:00:00Z",
    latest_simulation: sim(),
    ...overrides,
  };
}

describe("mapCandidatesToDashboard — 정상 시나리오(happy path)", () => {
  it("기대손실 오름차순으로 정렬하고, baseline 대비 절감액을 계산한다", () => {
    const baseline = candidate({
      id: 1,
      candidate_type: "baseline",
      description: "무대응 - 현재 계획대로 진행",
      latest_simulation: sim({ id: 1, candidate_id: 1, expected_loss: 200_000_000 }),
    });
    const better = candidate({
      id: 2,
      candidate_type: "단일",
      description: "[안전재고 사전 당김] 안전재고를 미리 당겨 확보한다",
      latest_simulation: sim({ id: 2, candidate_id: 2, expected_loss: 50_000_000 }),
    });
    const worse = candidate({
      id: 3,
      candidate_type: "단일",
      description: "[긴급 항공 전환] 수입부품을 항공으로 긴급 조달한다",
      latest_simulation: sim({ id: 3, candidate_id: 3, expected_loss: 120_000_000 }),
    });

    const result = mapCandidatesToDashboard([baseline, worse, better]);

    expect(result.candidates.map((c) => c.name)).toEqual(["안전재고 사전 당김", "긴급 항공 전환"]);
    expect(result.candidates[0].rank).toBe(1);
    expect(result.candidates[0].remainingLoss).toBe("0.5억원");
    // baseline 200,000,000 - better 50,000,000 = 150,000,000 절감
    expect(result.candidates[0].savingsAmount).toBe("-1.5억원");
    expect(result.candidates[0].mitigationRatio).toBe(75);
  });
});

describe("mapCandidatesToDashboard — 제외된 대응안", () => {
  it("validation_status가 '불가능'인 후보는 excludedCandidates로 분류되고 candidates에는 없다", () => {
    const infeasible = candidate({
      id: 4,
      candidate_type: "단일",
      description: "[대체 완성차 재고 배정] 다른 완성차 재고를 배정한다",
      validation_status: "불가능",
      exclusion_category: "자원부족",
      exclusion_detail: "가용 재고 없음",
      latest_simulation: null,
    });

    const result = mapCandidatesToDashboard([infeasible]);

    expect(result.candidates).toHaveLength(0);
    expect(result.excludedCandidates).toEqual([
      { id: 4, name: "대체 완성차 재고 배정", reason: "자원부족: 가용 재고 없음" },
    ]);
  });
});

describe("mapCandidatesToDashboard — 표시용 이름(name) 파생 로직", () => {
  it("description에 '[카테고리]' 접두어가 있으면 그 카테고리를 name으로 쓰고, description에서는 접두어를 제거한다", () => {
    const withCategory = candidate({
      id: 10,
      candidate_type: "복합",
      description: "[컨테이너 우선반출] 항만에서 컨테이너를 우선 반출한다",
    });

    const result = mapCandidatesToDashboard([withCategory]);

    expect(result.candidates[0].name).toBe("컨테이너 우선반출");
    expect(result.candidates[0].description).toBe("항만에서 컨테이너를 우선 반출한다");
  });

  it("description에 대괄호 접두어가 없으면(예: baseline) candidate_type 기반의 안전한 이름으로 대체하고 description은 그대로 둔다", () => {
    const baseline = candidate({
      id: 11,
      candidate_type: "baseline",
      description: "무대응 - 현재 계획대로 진행",
    });
    const noBracket = candidate({
      id: 12,
      candidate_type: "단일",
      description: "긴급운송으로 대응한다",
      latest_simulation: sim({ expected_loss: 10_000_000 }),
    });

    const result = mapCandidatesToDashboard([baseline, noBracket]);

    // baseline은 랭킹에는 없지만, name 파생 로직 자체는 excludedCandidates 경로로도 검증한다
    const excludedBaselineLike = mapCandidatesToDashboard([
      { ...baseline, validation_status: "불가능" },
    ]);
    expect(excludedBaselineLike.excludedCandidates[0].name).toBe("무대응(기준선)");

    expect(result.candidates[0].name).toBe("단일");
    expect(result.candidates[0].description).toBe("긴급운송으로 대응한다");
  });

  it("서로 다른 카테고리를 가진 두 '단일' 후보의 이름이 더 이상 충돌하지 않는다", () => {
    const containerFirst = candidate({
      id: 20,
      candidate_type: "단일",
      description: "[컨테이너 우선반출] 설명 A",
      latest_simulation: sim({ id: 20, candidate_id: 20, expected_loss: 10_000_000 }),
    });
    const emergencyTransport = candidate({
      id: 21,
      candidate_type: "단일",
      description: "[긴급운송] 설명 B",
      latest_simulation: sim({ id: 21, candidate_id: 21, expected_loss: 20_000_000 }),
    });

    const result = mapCandidatesToDashboard([containerFirst, emergencyTransport]);
    const names = result.candidates.map((c) => c.name);

    expect(names).toEqual(["컨테이너 우선반출", "긴급운송"]);
    expect(new Set(names).size).toBe(names.length);
  });

  it("대괄호가 비어있거나([]) 닫히지 않은 경우 candidate_type으로 안전하게 대체한다", () => {
    const emptyBracket = candidate({
      id: 30,
      candidate_type: "단일",
      description: "[] 카테고리 없이 온 경우",
      latest_simulation: sim({ expected_loss: 5_000_000 }),
    });
    const unclosedBracket = candidate({
      id: 31,
      candidate_type: "복합",
      description: "[대체부품 닫히지 않은 대괄호 설명",
      latest_simulation: sim({ expected_loss: 6_000_000 }),
    });

    const result = mapCandidatesToDashboard([emptyBracket, unclosedBracket]);

    // expected_loss 오름차순 정렬: emptyBracket(5,000,000) → unclosedBracket(6,000,000)
    const [empty, unclosed] = result.candidates;

    expect(empty.name).toBe("단일");
    expect(empty.description).toBe("[] 카테고리 없이 온 경우");
    expect(unclosed.name).toBe("복합");
    expect(unclosed.description).toBe("[대체부품 닫히지 않은 대괄호 설명");
  });
});

describe("mapCandidatesToDashboard — 경계값", () => {
  it("아직 시뮬레이션이 실행되지 않은 후보(latest_simulation=null)는 랭킹에서 제외한다", () => {
    const unsimulated = candidate({ id: 5, latest_simulation: null });
    const result = mapCandidatesToDashboard([unsimulated]);
    expect(result.candidates).toHaveLength(0);
    expect(result.excludedCandidates).toHaveLength(0);
  });

  it("baseline이 없거나 baseline에 시뮬레이션 결과가 없으면 절감액을 '-'로 표시하고 완화율은 0이다", () => {
    const onlyOne = candidate({ id: 6, latest_simulation: sim({ expected_loss: 90_000_000 }) });
    const result = mapCandidatesToDashboard([onlyOne]);

    expect(result.candidates[0].savingsAmount).toBe("-");
    expect(result.candidates[0].mitigationRatio).toBe(0);
  });

  it("baseline 후보 자신은 랭킹 목록에 포함하지 않는다", () => {
    const baseline = candidate({ id: 7, candidate_type: "baseline" });
    const result = mapCandidatesToDashboard([baseline]);
    expect(result.candidates).toHaveLength(0);
  });
});

describe("mapCandidatesToDashboard — 필드 매핑", () => {
  it("p90/cvar/confidence/sensitivity_variables/fact/inference/assumption을 detail로 매핑한다", () => {
    const withDetail = candidate({
      id: 8,
      latest_simulation: sim({
        p90: 150_000_000,
        cvar: 180_000_000,
        confidence: 0.72,
        sensitivity_variables: ["재고 소진 속도"],
        fact: { a: 1 },
        inference: { b: 2 },
        assumption: { c: 3 },
      }),
    });

    const result = mapCandidatesToDashboard([withDetail]);
    const detail = result.candidates[0].detail;

    expect(detail).toEqual({
      p90: "1.5억원",
      cvar: "1.8억원",
      confidencePercent: 72,
      sensitivityVariables: ["재고 소진 속도"],
      fact: { a: 1 },
      inference: { b: 2 },
      assumption: { c: 3 },
    });
  });
});
