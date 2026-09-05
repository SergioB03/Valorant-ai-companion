// @vitest-environment jsdom
//
// analytics.js keeps module-level state (queue, DNT flag, flush interval), so
// every test imports a fresh copy via vi.resetModules() + dynamic import,
// with fake timers driving the 10s flush interval.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let fetchMock;

async function importAnalytics() {
  vi.resetModules();
  return import("./analytics.js");
}

function setDNT(value) {
  Object.defineProperty(window.navigator, "doNotTrack", {
    value,
    configurable: true,
  });
}

function sentBody(call) {
  return JSON.parse(call[1].body);
}

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock = vi.fn(() => Promise.resolve({ ok: true }));
  vi.stubGlobal("fetch", fetchMock);
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  delete window.navigator.doNotTrack;
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("analytics with Do Not Track", () => {
  it("sends nothing and creates no ids", async () => {
    setDNT("1");
    const { track, trackSessionStart } = await importAnalytics();
    trackSessionStart();
    for (let i = 0; i < 20; i++) track("event", { i });
    await vi.advanceTimersByTimeAsync(30_000);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(localStorage.getItem("vac:vid")).toBeNull();
    expect(sessionStorage.getItem("vac:sid")).toBeNull();
  });
});

describe("analytics queue", () => {
  it("flushes a batch at 10 events with ids and pathname only", async () => {
    const { track } = await importAnalytics();
    for (let i = 0; i < 10; i++) track("tab_change", { tab: "meta" });
    await vi.advanceTimersByTimeAsync(0);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = sentBody(fetchMock.mock.calls[0]);
    expect(body.events).toHaveLength(10);
    expect(body.visitor_id).toBe(localStorage.getItem("vac:vid"));
    expect(body.session_id).toBe(sessionStorage.getItem("vac:sid"));
    for (const ev of body.events) {
      // The privacy contract: events carry the pathname only — never the
      // query string a shared ?player=Name%23TAG URL would expose.
      expect(ev.path).toBe("/");
      expect(JSON.stringify(ev)).not.toContain("player=");
    }
  });

  it("retries a failed batch exactly once, then drops it", async () => {
    fetchMock.mockImplementation(() => Promise.reject(new Error("down")));
    const { track } = await importAnalytics();
    for (let i = 0; i < 10; i++) track("event", { i });
    await vi.advanceTimersByTimeAsync(0); // first attempt fails, requeued
    await vi.advanceTimersByTimeAsync(10_000); // retry fails, dropped
    await vi.advanceTimersByTimeAsync(20_000); // nothing left to send
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const first = sentBody(fetchMock.mock.calls[0]);
    const second = sentBody(fetchMock.mock.calls[1]);
    expect(second.events).toEqual(first.events);
  });

  it("caps the queue at 50 events, dropping the oldest", async () => {
    // First flush hangs so everything after it piles into the queue.
    let release;
    fetchMock.mockImplementationOnce(
      () => new Promise((resolve) => (release = resolve)),
    );
    const { track } = await importAnalytics();
    for (let i = 0; i < 10; i++) track("early", { i });
    await vi.advanceTimersByTimeAsync(0); // 10 in flight, hanging
    for (let i = 0; i < 70; i++) track("late", { i }); // 20 over the cap

    release({ ok: true });
    await vi.advanceTimersByTimeAsync(10_000);
    await vi.advanceTimersByTimeAsync(10_000);
    await vi.advanceTimersByTimeAsync(10_000);

    // 10 in-flight + two full 25-event batches = the 50-event cap held.
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const delivered = fetchMock.mock.calls
      .slice(1)
      .flatMap((call) => sentBody(call).events);
    expect(delivered).toHaveLength(50);
    // The oldest of the 70 were dropped: the survivors are the last 50.
    expect(delivered[0].props.i).toBe(20);
    expect(delivered[49].props.i).toBe(69);
  });
});
