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
    candidate_type: "안전재고 사전 당김",
    description: "설명",
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
      latest_simulation: sim({ id: 1, candidate_id: 1, expected_loss: 200_000_000 }),
    });
    const better = candidate({
      id: 2,
      candidate_type: "안전재고 사전 당김",
      latest_simulation: sim({ id: 2, candidate_id: 2, expected_loss: 50_000_000 }),
    });
    const worse = candidate({
      id: 3,
      candidate_type: "긴급 항공 전환",
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
      candidate_type: "대체 완성차 재고 배정",
      validation_status: "불가능",
      exclusion_category: "자원부족",
      exclusion_detail: "가용 재고 없음",
      latest_simulation: null,
    });

    const result = mapCandidatesToDashboard([infeasible]);

    expect(result.candidates).toHaveLength(0);
    expect(result.excludedCandidates).toEqual([
      { name: "대체 완성차 재고 배정", reason: "자원부족: 가용 재고 없음" },
    ]);
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
