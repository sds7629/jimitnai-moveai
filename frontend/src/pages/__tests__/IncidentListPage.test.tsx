import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { IncidentListPage } from "../IncidentListPage";
import { listIncidents } from "../../features/incidents/api";
import type { IncidentListItem } from "../../features/incidents/types";

vi.mock("../../features/incidents/api");
const mockListIncidents = vi.mocked(listIncidents);

const sample: IncidentListItem[] = [
  {
    id: 1,
    type: "항만 적체",
    location: "부산항 3부두",
    occurred_at: "2026-08-13T00:00:00Z",
    status: "유효",
    duplicate_of_incident_id: null,
    created_at: "2026-08-13T00:00:00Z",
  },
  {
    id: 2,
    type: "항만 파업",
    location: "부산항",
    occurred_at: "2026-08-13T02:00:00Z",
    status: "유효",
    duplicate_of_incident_id: null,
    created_at: "2026-08-13T02:00:00Z",
  },
  {
    id: 3,
    type: "관세 규정 변경",
    location: "인천세관",
    occurred_at: "2026-08-13T04:00:00Z",
    status: "유효",
    duplicate_of_incident_id: null,
    created_at: "2026-08-13T04:00:00Z",
  },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <IncidentListPage />
    </MemoryRouter>,
  );
}

describe("IncidentListPage — 정상 시나리오(happy path)", () => {
  it("시드 3종 사건을 불러와 각각 클릭 가능한 카드로 렌더링한다", async () => {
    mockListIncidents.mockResolvedValue(sample);
    renderPage();

    expect(await screen.findByText("항만 적체")).toBeInTheDocument();
    expect(screen.getByText("항만 파업")).toBeInTheDocument();
    expect(screen.getByText("관세 규정 변경")).toBeInTheDocument();

    const link = screen.getByText("항만 적체").closest("a");
    expect(link).toHaveAttribute("href", "/incidents/1");
  });
});

describe("IncidentListPage — 로딩 상태", () => {
  it("응답이 오기 전에는 로딩 문구를 표시한다", () => {
    mockListIncidents.mockReturnValue(new Promise(() => {})); // 영원히 pending
    renderPage();

    expect(screen.getByText(/불러오는 중/)).toBeInTheDocument();
  });
});

describe("IncidentListPage — 예외 케이스", () => {
  it("API 호출이 실패하면 에러 메시지를 표시한다", async () => {
    mockListIncidents.mockRejectedValue(new Error("네트워크 오류"));
    renderPage();

    expect(await screen.findByText(/불러오지 못했습니다/)).toBeInTheDocument();
  });
});

describe("IncidentListPage — 경계값(빈 목록)", () => {
  it("사건이 0건이면 빈 상태 문구를 표시한다", async () => {
    mockListIncidents.mockResolvedValue([]);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/표시할 사건이 없습니다/)).toBeInTheDocument();
    });
  });
});
