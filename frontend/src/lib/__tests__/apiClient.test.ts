import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiGet, apiPost } from "../apiClient";

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
