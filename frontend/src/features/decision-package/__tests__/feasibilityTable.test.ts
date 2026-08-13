import { describe, expect, it } from "vitest";
import { buildFeasibilityTable } from "../feasibilityTable";
import type { FeasibilityAndExclusionSection, KeySensitivityVariablesSection } from "../types";

describe("buildFeasibilityTable — 정상 시나리오(happy path)", () => {
  it("검증 상태·제외 사유·선행 조건·민감도 변수를 후보별로 합친다", () => {
    const feasibility: FeasibilityAndExclusionSection = {
      "1": {
        validation_status: "가능",
        exclusion_category: null,
        exclusion_detail: null,
        preconditions: ["창고 여유 확보"],
        has_simulation_result: true,
      },
    };
    const sensitivity: KeySensitivityVariablesSection = { "1": ["항만 재개방 시점", "환율"] };

    const rows = buildFeasibilityTable(feasibility, sensitivity);

    expect(rows).toHaveLength(1);
    expect(rows[0]).toEqual({
      candidateId: "1",
      validationStatus: "가능",
      exclusionCategory: null,
      exclusionDetail: null,
      preconditions: ["창고 여유 확보"],
      sensitivityVariables: ["항만 재개방 시점", "환율"],
    });
  });
});

describe("buildFeasibilityTable — 경계값(제외된 후보, 민감도 변수 없음)", () => {
  it("불가능 판정 후보는 exclusion 정보를 포함하고, 시뮬레이션 안 된 후보는 민감도 변수가 빈 배열이다", () => {
    const feasibility: FeasibilityAndExclusionSection = {
      "2": {
        validation_status: "불가능",
        exclusion_category: "자원부족",
        exclusion_detail: "가용 창고 없음",
        preconditions: [],
        has_simulation_result: false,
      },
    };

    const rows = buildFeasibilityTable(feasibility, {});

    expect(rows[0].exclusionCategory).toBe("자원부족");
    expect(rows[0].exclusionDetail).toBe("가용 창고 없음");
    expect(rows[0].sensitivityVariables).toEqual([]);
  });
});

describe("buildFeasibilityTable — 실패 시나리오(빈 섹션)", () => {
  it("두 섹션 다 비어 있으면 빈 배열을 반환한다", () => {
    expect(buildFeasibilityTable({}, {})).toEqual([]);
  });
});
