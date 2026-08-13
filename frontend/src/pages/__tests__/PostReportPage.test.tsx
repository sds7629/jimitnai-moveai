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
    "1_사건_개요와_발생시점": { incident_type: "항만 파업" },
    "2_최초_예상과_실제_진행_과정": {},
    "3_주요_동적_변수의_변화": {},
    "4_검토한_대응안과_제외_사유": {},
    "5_최종_결정과_승인자": {},
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
    expect(screen.getByText(/미확정/)).toBeInTheDocument();
    expect(screen.getByText(/실적 확정값을 입력받는 API가 없습니다/)).toBeInTheDocument();
    expect(screen.getByText("1. 사건 개요와 발생시점")).toBeInTheDocument();
    expect(screen.getByText("12. 향후 SOP·모델·데이터 개선사항")).toBeInTheDocument();
    expect(screen.getByText("직접 손익 효과")).toBeInTheDocument();
    expect(screen.getByText("5.0억원")).toBeInTheDocument();
    expect(screen.getByText(/법무 판단을 대체하지 않습니다/)).toBeInTheDocument();
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
