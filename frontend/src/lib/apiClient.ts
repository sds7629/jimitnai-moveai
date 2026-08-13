/**
 * 최소 fetch 래퍼.
 *
 * frontend/docs/FEATURE_PHASES.md Phase 1 결정: 지금은 openapi-fetch를 도입하지 않는다 —
 * 백엔드 OpenAPI 스펙이 아직 안정되지 않은 상태라 스펙이 바뀔 때마다 재생성 비용이 든다.
 * 엔드포인트가 여러 개 붙기 시작하면(Phase 2~3 완료 후) 도입을 재검토한다.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new ApiError(response.status, `GET ${path} 실패 (status ${response.status})`);
  }
  return (await response.json()) as T;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new ApiError(response.status, `POST ${path} 실패 (status ${response.status})`);
  }
  return (await response.json()) as T;
}
