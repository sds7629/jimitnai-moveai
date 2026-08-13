import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiGet, apiPatch, apiPost } from "../apiClient";

describe("apiGet", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("응답이 정상이면 JSON을 파싱해서 반환한다", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [{ id: 1 }],
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await apiGet<{ id: number }[]>("/incidents");
    expect(result).toEqual([{ id: 1 }]);
  });

  it("응답이 실패(4xx/5xx)이면 ApiError를 던진다", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", mockFetch);

    await expect(apiGet("/incidents")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("apiPost", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("POST 요청을 보내고 응답 JSON을 반환한다", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ candidate_count: 2 }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await apiPost<{ candidate_count: number }>("/incidents/1/simulate");
    expect(result).toEqual({ candidate_count: 2 });
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/incidents/1/simulate",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("응답이 실패(4xx/5xx)이면 ApiError를 던진다", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", mockFetch);

    await expect(apiPost("/incidents/1/simulate")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("apiPatch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("PATCH 요청을 body와 함께 보내고 응답 JSON을 반환한다", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: "수신" }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await apiPatch<{ status: string }>("/sop/1/status", { status: "수신", actor: "김담당" });
    expect(result).toEqual({ status: "수신" });
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/sop/1/status",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ status: "수신", actor: "김담당" }) }),
    );
  });

  it("응답이 실패(4xx/5xx)이면 ApiError를 던진다", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", mockFetch);

    await expect(apiPatch("/sop/1/status", { status: "수신", actor: "김담당" })).rejects.toBeInstanceOf(ApiError);
  });
});

// 내부 REST 경로/HTTP 메서드가 사용자에게 노출되는 에러 배너(IncidentContextBar/ApprovalPanel/
// SopDispatchPanel/IncidentListPage/IncidentDetailPage/PostReportPage/RoiPage)에 그대로
// 새어나가지 않는지 검증한다 — 이 화면들은 모두 catch한 error.message를 그대로 렌더링한다.
describe("ApiError.message — 내부 라우팅 정보 노출 방지", () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    consoleErrorSpy.mockRestore();
  });

  it("GET 실패 시 .message에 내부 경로나 'GET'이 포함되지 않는다", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", mockFetch);

    await expect(apiGet("/incidents/3/simulate")).rejects.toSatisfy((error: unknown) => {
      const message = (error as ApiError).message;
      return !message.includes("/incidents/3/simulate") && !/\bGET\b/.test(message);
    });
  });

  it(".message는 사용자에게 의미 있는 상태 코드를 여전히 담고 있다", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", mockFetch);

    await expect(apiGet("/incidents/3/simulate")).rejects.toSatisfy((error: unknown) => {
      const apiError = error as ApiError;
      return apiError.status === 500 && apiError.message.includes("500");
    });
  });

  it("POST/PATCH 실패 시에도 .message에 내부 경로나 HTTP 메서드가 포함되지 않는다", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", mockFetch);

    await expect(apiPost("/incidents/3/simulate")).rejects.toSatisfy((error: unknown) => {
      const message = (error as ApiError).message;
      return !message.includes("/incidents/3/simulate") && !/\bPOST\b/.test(message);
    });

    await expect(
      apiPatch("/sop/1/status", { status: "수신", actor: "김담당" }),
    ).rejects.toSatisfy((error: unknown) => {
      const message = (error as ApiError).message;
      return !message.includes("/sop/1/status") && !/\bPATCH\b/.test(message);
    });
  });

  it("메서드+경로 등 디버깅용 상세 정보는 console.error로는 남긴다", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", mockFetch);

    await expect(apiGet("/incidents/3/simulate")).rejects.toBeInstanceOf(ApiError);

    expect(consoleErrorSpy).toHaveBeenCalledWith(expect.stringContaining("GET"));
    expect(consoleErrorSpy).toHaveBeenCalledWith(expect.stringContaining("/incidents/3/simulate"));
  });
});
