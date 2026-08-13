import { useEffect, useRef } from "react";
import { API_BASE_URL } from "../../lib/apiClient";

export interface IncidentStreamHandlers {
  onDagUpdated?: () => void;
  onDecisionPackageUpdated?: () => void;
  onDeadlineOverrun?: () => void;
}

/**
 * GET /incidents/{id}/stream (SSE) 구독 훅.
 *
 * backend/app/api/stream.py가 2~3초 간격 폴링으로 push하는 이벤트 3종
 * (decision_package_updated / dag_updated / deadline_overrun)을 그대로 구독한다.
 * TanStack Query 없이 지금 구조(로컬 useState + fetch 재호출)를 그대로 쓰기 때문에, 이벤트가 오면
 * 호출부가 넘겨준 콜백(보통 기존 재조회 함수)을 그냥 실행하는 방식으로 연결한다 — "필요한 부분만
 * invalidate"까지는 아니지만, 사건 하나 안에서 조회하는 리소스가 아직 5개뿐이라 전체 재조회 비용이
 * 크지 않다 (frontend/docs/FEATURE_PHASES.md Phase 8).
 */
export function useIncidentStream(incidentId: number, handlers: IncidentStreamHandlers): void {
  // handlers가 매 렌더마다 새 객체로 넘어와도 재연결하지 않도록 ref로 최신 값만 추적한다
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    const source = new EventSource(`${API_BASE_URL}/incidents/${incidentId}/stream`);

    source.addEventListener("dag_updated", () => handlersRef.current.onDagUpdated?.());
    source.addEventListener("decision_package_updated", () => handlersRef.current.onDecisionPackageUpdated?.());
    source.addEventListener("deadline_overrun", () => handlersRef.current.onDeadlineOverrun?.());

    return () => source.close();
  }, [incidentId]);
}
