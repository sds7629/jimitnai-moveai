import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useIncidentStream } from "../useIncidentStream";

/** jsdom에는 EventSource가 구현돼 있지 않아서 최소 기능만 흉내내는 가짜로 대체한다 */
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  closed = false;
  private listeners: Record<string, ((e: MessageEvent) => void)[]> = {};

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (e: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(handler);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: unknown) {
    for (const handler of this.listeners[type] ?? []) {
      handler({ data: JSON.stringify(data) } as MessageEvent);
    }
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useIncidentStream — 정상 시나리오(happy path)", () => {
  it("사건 ID로 스트림 URL을 연결하고, dag_updated 이벤트가 오면 onDagUpdated를 호출한다", () => {
    const onDagUpdated = vi.fn();
    renderHook(() => useIncidentStream(2, { onDagUpdated }));

    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toBe("http://localhost:8000/incidents/2/stream");

    FakeEventSource.instances[0].emit("dag_updated", { type: "dag_updated", incident_id: 2, snapshot_id: 9 });
    expect(onDagUpdated).toHaveBeenCalledTimes(1);
  });

  it("decision_package_updated 이벤트가 오면 onDecisionPackageUpdated를 호출한다", () => {
    const onDecisionPackageUpdated = vi.fn();
    renderHook(() => useIncidentStream(2, { onDecisionPackageUpdated }));

    FakeEventSource.instances[0].emit("decision_package_updated", { type: "decision_package_updated" });
    expect(onDecisionPackageUpdated).toHaveBeenCalledTimes(1);
  });

  it("deadline_overrun 이벤트가 오면 onDeadlineOverrun을 호출한다", () => {
    const onDeadlineOverrun = vi.fn();
    renderHook(() => useIncidentStream(2, { onDeadlineOverrun }));

    FakeEventSource.instances[0].emit("deadline_overrun", { type: "deadline_overrun" });
    expect(onDeadlineOverrun).toHaveBeenCalledTimes(1);
  });
});

describe("useIncidentStream — 정리(cleanup)", () => {
  it("언마운트되면 EventSource를 닫는다", () => {
    const { unmount } = renderHook(() => useIncidentStream(2, {}));
    const instance = FakeEventSource.instances[0];

    unmount();

    expect(instance.closed).toBe(true);
  });
});

describe("useIncidentStream — 경계값(사건 ID 변경)", () => {
  it("incidentId가 바뀌면 기존 연결을 닫고 새 URL로 다시 연결한다", () => {
    const { rerender } = renderHook(({ id }) => useIncidentStream(id, {}), { initialProps: { id: 2 } });

    rerender({ id: 3 });

    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.instances[0].closed).toBe(true);
    expect(FakeEventSource.instances[1].url).toBe("http://localhost:8000/incidents/3/stream");
  });
});
