import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { PostReportPage } from "../PostReportPage";
import { getCostAttribution, getPostReport } from "../../features/post-report/api";
import type { CostAttributionApi, PostReportApi } from "../../features/post-report/types";

vi.mock("../../features/post-report/api");
const mockGetPostReport = vi.mocked(getPostReport);
const mockGetCostAttribution = vi.mocked(getCostAttribution);

const postReport: PostReportApi = {
  incident_id: 2,
  report_status: "잠정",
  actual_status: "미확정",
  scope_limitation_note: "이 시스템에는 실적 확정값을 입력받는 API가 없습니다.",
  generated_at: "2026-08-13T05:00:00Z",
  sections: {
    "1_사건_개요와_발생시점": {
      incident_id: 2,
      type: "항만 파업",
      location: "부산항",
      occurred_at: "2026-08-10T00:00:00Z",
      status: "진행중",
      duplicate_of_incident_id: null,
      affected_targets: {},
      assumptions_at_intake: [],
      created_at: "2026-08-10T00:10:00Z",
    },
    "2_최초_예상과_실제_진행_과정": {
      expected: {
        baseline: {
          available: true,
          candidate_id: 1,
          candidate_type: "무대응",
          description: "아무 조치도 하지 않음",
          start_time_variant: null,
          simulation: {
            available: true,
            expected_loss: 1_200_000_000,
            p90: 1_800_000_000,
            cvar: 2_100_000_000,
            confidence: 0.82,
            data_version: "d1",
            scenario_version: "s1",
            calculated_at: "2026-08-10T01:00:00Z",
          },
        },
        approved_candidate: { available: false },
      },
      actual_status: "미확정",
      actual_progress: { available: false, reason: "실제 진행 실적을 입력받는 API가 없습니다." },
    },
    "3_주요_동적_변수의_변화": {
      snapshot_count: 1,
      versions: [
        {
          snapshot_id: 10,
          data_version: "d1",
          scenario_version: "s1",
          quality_mode: "limited",
          freshness_seconds: 7200,
          coverage_ratio: 0.4,
          assumptions: ["선복 확보 지연"],
          created_at: "2026-08-10T01:00:00Z",
        },
      ],
      changes_summary: ["스냅샷이 1개뿐이라 버전 간 변화 이력이 없음 (최초 스냅샷만 존재)"],
    },
    "4_검토한_대응안과_제외_사유": {},
    "5_최종_결정과_승인자": {
      approvals_history: [],
      final_decision: { available: false, reason: "이 사건에 대한 승인/반려 이력(approvals)이 없음" },
    },
    "6_SOP_발송_수신_수락_실행_이력": {},
    "7_예상_손실과_실제_손실": {},
    "8_회피한_손실과_추가_발생_비용": {},
    "9_LD_DND_귀책_및_비용_부담_주체": {},
    "10_시뮬레이션_오차와_가정의_영향": {},
    "11_자원_확보_실패_실행_편차와_에스컬레이션_이력": {},
    "12_향후_SOP_모델_데이터_개선사항": {},
  },
};

const costAttribution: CostAttributionApi = {
  incident_id: 2,
  is_heuristic: true,
  rag_unavailable: false,
  heuristic_disclaimer: "법무 판단을 대체하지 않습니다.",
  avoided_loss_basis: {},
  matched_ld_clauses: [],
  matched_dnd_clauses: [],
  breakdown: { 직접_손익_효과: 0, 고객_회피비용: 0, 분쟁_협상_가능_금액: 500_000_000 },
  classification_note: "귀책 판단 근거가 없어 분쟁·협상 가능 금액으로 분류했습니다.",
};

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/incidents/${id}/post-report`]}>
      <Routes>
        <Route path="/incidents/:id/post-report" element={<PostReportPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PostReportPage — 정상 시나리오(happy path)", () => {
  it("잠정 상태 배지와 12개 섹션, 비용 귀속 3분류를 모두 렌더링한다", async () => {
    mockGetPostReport.mockResolvedValue(postReport);
    mockGetCostAttribution.mockResolvedValue(costAttribution);

    renderAt("2");

    expect(await screen.findByText("잠정")).toBeInTheDocument();
    // Phase 20 이후 "미확정"은 예상 진행 카드에도 나오므로 상단 실적 배지를 정규식으로 특정한다
    expect(screen.getByText(/실적: 미확정/)).toBeInTheDocument();
    expect(screen.getByText(/실적 확정값을 입력받는 API가 없습니다/)).toBeInTheDocument();
    // 1번(사건 개요)·5번(최종 결정) 섹션은 Phase 19에서 OverviewAndDecisionCard로 옮겨져
    // 더 이상 raw label로 나오지 않고 실제 값(항만 파업)으로 렌더링된다
    expect(screen.getByText("항만 파업")).toBeInTheDocument();
    expect(screen.getByText("12. 향후 SOP·모델·데이터 개선사항")).toBeInTheDocument();
    expect(screen.getByText("직접 손익 효과")).toBeInTheDocument();
    expect(screen.getByText("5.0억원")).toBeInTheDocument();
    expect(screen.getByText(/법무 판단을 대체하지 않습니다/)).toBeInTheDocument();
  });
});

describe("PostReportPage — 사건 개요·최종 결정 카드", () => {
  it("1번·5번 섹션은 JSON이 아니라 OverviewAndDecisionCard로 렌더링한다", async () => {
    mockGetPostReport.mockResolvedValue(postReport);
    mockGetCostAttribution.mockResolvedValue(costAttribution);

    renderAt("2");

    expect(await screen.findByText("사건 개요 · 최종 결정")).toBeInTheDocument();
    expect(screen.getByText(/승인\/반려 이력/)).toBeInTheDocument();
    expect(screen.queryByText("1. 사건 개요와 발생시점")).not.toBeInTheDocument();
    expect(screen.queryByText("5. 최종 결정과 승인자")).not.toBeInTheDocument();
  });
});

describe("PostReportPage — 예상 진행·동적 변수 변화 카드", () => {
  it("2번·3번 섹션은 JSON이 아니라 ExpectedProgressAndChanges로 렌더링한다", async () => {
    mockGetPostReport.mockResolvedValue(postReport);
    mockGetCostAttribution.mockResolvedValue(costAttribution);

    renderAt("2");

    expect(await screen.findByText("최초 예상 · 실제 진행 · 동적 변수 변화")).toBeInTheDocument();
    expect(screen.getByText("무대응")).toBeInTheDocument();
    expect(screen.getByText("12.0억원")).toBeInTheDocument();
    expect(screen.getByText("해당 후보 없음")).toBeInTheDocument();
    expect(screen.getByText(/실제 진행: 미확정/)).toBeInTheDocument();
    expect(screen.getByText("제한 모드")).toBeInTheDocument();
    expect(screen.getByText("커버리지 40%")).toBeInTheDocument();
    expect(screen.getByText(/스냅샷이 1개뿐이라/)).toBeInTheDocument();
    expect(screen.queryByText("2. 최초 예상과 실제 진행 과정")).not.toBeInTheDocument();
    expect(screen.queryByText("3. 주요 동적 변수의 변화")).not.toBeInTheDocument();
  });

  it("섹션 값이 비어 있어도 기본값으로 오류 없이 렌더링한다", async () => {
    mockGetPostReport.mockResolvedValue({
      ...postReport,
      sections: { ...postReport.sections, "2_최초_예상과_실제_진행_과정": {}, "3_주요_동적_변수의_변화": {} },
    });
    mockGetCostAttribution.mockResolvedValue(costAttribution);

    renderAt("2");

    expect(await screen.findByText("최초 예상 · 실제 진행 · 동적 변수 변화")).toBeInTheDocument();
    expect(screen.getAllByText("해당 후보 없음")).toHaveLength(2);
    expect(screen.getByText("스냅샷 이력이 없습니다.")).toBeInTheDocument();
  });
});

describe("PostReportPage — 로딩 상태", () => {
  it("응답이 오기 전에는 로딩 문구를 표시한다", () => {
    mockGetPostReport.mockReturnValue(new Promise(() => {}));
    mockGetCostAttribution.mockReturnValue(new Promise(() => {}));

    renderAt("2");

    expect(screen.getByText(/불러오는 중/)).toBeInTheDocument();
  });
});

describe("PostReportPage — 예외 케이스", () => {
  it("사후보고서 조회가 실패하면 에러 메시지를 표시한다", async () => {
    mockGetPostReport.mockRejectedValue(new Error("존재하지 않는 사건"));
    mockGetCostAttribution.mockResolvedValue(costAttribution);

    renderAt("999");

    expect(await screen.findByText(/불러오지 못했습니다/)).toBeInTheDocument();
  });

  it("비용 귀속 조회가 실패해도 에러 메시지를 표시한다", async () => {
    mockGetPostReport.mockResolvedValue(postReport);
    mockGetCostAttribution.mockRejectedValue(new Error("조회 실패"));

    renderAt("2");

    expect(await screen.findByText(/불러오지 못했습니다/)).toBeInTheDocument();
  });
});

describe("PostReportPage — 경계값(귀속 금액 없음)", () => {
  it("breakdown 값이 null이면 '-'로 표시한다", async () => {
    mockGetPostReport.mockResolvedValue(postReport);
    mockGetCostAttribution.mockResolvedValue({
      ...costAttribution,
      breakdown: { 직접_손익_효과: null, 고객_회피비용: null, 분쟁_협상_가능_금액: null },
    });

    renderAt("2");

    expect(await screen.findAllByText("-")).not.toHaveLength(0);
  });
});
