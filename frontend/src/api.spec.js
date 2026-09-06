// @vitest-environment jsdom
//
// Two contracts live in api.js:
//
// 1. Demo mode (Wave 2): a module-level flag short-circuits EVERY endpoint
//    against the fixtures module — the demo player must never reach the
//    network (/mental/coach spends Claude money even on failed lookups).
//    Asserted via a mocked fetch that must never be called.
//
// 2. Quota headers (Wave 2): the daily-quota state is keyed ONLY on
//    X-Quota-Exhausted (three different 429s exist), Retry-After rides into
//    err.retryAfterSeconds, and X-Quota-Limit is remembered from successes
//    and 429s alike so captions never hardcode a limit.
//
// api.js keeps module state (demo flag, last-seen quota limit) and imports
// analytics.js (also module state), so every test gets a fresh copy via
// vi.resetModules() + dynamic import, with DNT set so analytics stays inert.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let fetchMock;

async function importApi() {
  vi.resetModules();
  return import("./api.js");
}

function setDNT(value) {
  Object.defineProperty(window.navigator, "doNotTrack", {
    value,
    configurable: true,
  });
}

function jsonRes({ status = 200, headers = {}, body = {} } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: async () => body,
  };
}

beforeEach(() => {
  setDNT("1"); // keep analytics from queueing api_error events through fetch
  fetchMock = vi.fn(() => Promise.resolve(jsonRes()));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  delete window.navigator.doNotTrack;
  vi.unstubAllGlobals();
});

describe("demo mode short-circuits every endpoint", () => {
  it("resolves all seven endpoints without a single fetch", async () => {
    const api = await importApi();
    api.setDemoMode(true);
    expect(api.isDemoMode()).toBe(true);

    const [account, matches, analysis, tilt, coach, profile, meta] =
      await Promise.all([
        api.getAccount("Demo", "VAC"),
        api.getMatches("Demo", "VAC", "na", 10),
        api.analyzeMatches("Demo", "VAC", "na", 10),
        api.tiltCheck("Demo", "VAC", "na", 10),
        api.coachChat("Demo", "VAC", "na", "hi", []),
        api.getMentalProfile("Demo", "VAC"),
        api.askMeta("what changed?"),
      ]);

    expect(fetchMock).not.toHaveBeenCalled();

    // Clearly fake identity, believable data.
    expect(account.data.name).toBe("Demo");
    expect(account.data.tag).toBe("VAC");
    expect(matches).toHaveLength(10);
    for (const m of matches) {
      expect(m.map).toBeTruthy();
      expect(m.agent).toBeTruthy();
      expect(typeof m.kills).toBe("number");
      expect(typeof m.won).toBe("boolean");
    }
    // The wow configuration: ~55 "heated" so the Omen pulse + signals show.
    expect(tilt.tilt_level).toBe("heated");
    expect(tilt.tilt_score).toBeGreaterThanOrEqual(50);
    expect(tilt.tilt_score).toBeLessThanOrEqual(74);
    expect(tilt.signals.length).toBeGreaterThan(0);
    expect(tilt.coach_message).toMatch(/\w/);
    expect(analysis.analysis.overview).toMatch(/\w/);
    expect(Array.isArray(analysis.analysis.strengths)).toBe(true);
    expect(Array.isArray(analysis.analysis.weaknesses)).toBe(true);
    expect(analysis.match_count).toBe(10);
    expect(coach.reply).toMatch(/\w/);
    expect(profile.snapshots.length).toBeGreaterThan(1);
    expect(meta.answer).toMatch(/\w/);
    expect(meta.sources.length).toBeGreaterThan(0);
  });

  it("uses the network again once demo mode is off", async () => {
    const api = await importApi();
    api.setDemoMode(true);
    await api.getAccount("Demo", "VAC");
    expect(fetchMock).not.toHaveBeenCalled();

    api.setDemoMode(false);
    await api.getAccount("Jett", "1234");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toContain("/riot/account/Jett/1234");
  });
});

describe("quota header parsing", () => {
  it("lifts X-Quota-Exhausted, Retry-After and X-Quota-Limit off a daily-quota 429", async () => {
    const api = await importApi();
    fetchMock.mockResolvedValueOnce(
      jsonRes({
        status: 429,
        headers: {
          "X-Quota-Exhausted": "1",
          "Retry-After": "7200",
          "X-Quota-Limit": "25",
        },
        body: { detail: "Daily free AI quota reached" },
      }),
    );
    const err = await api.askMeta("q").catch((e) => e);
    expect(err.status).toBe(429);
    expect(err.quotaExhausted).toBe(true);
    expect(err.retryAfterSeconds).toBe(7200);
    expect(api.getQuotaLimit()).toBe(25);
  });

  it("a bare per-minute 429 is NOT the quota-exhausted state", async () => {
    const api = await importApi();
    fetchMock.mockResolvedValueOnce(
      jsonRes({ status: 429, body: { detail: "Rate limit exceeded: 10/minute" } }),
    );
    const err = await api.tiltCheck("A", "B").catch((e) => e);
    expect(err.status).toBe(429);
    expect(err.quotaExhausted).toBe(false);
    expect(err.retryAfterSeconds).toBeUndefined();
  });

  it("remembers X-Quota-Limit from successful responses too", async () => {
    const api = await importApi();
    expect(api.getQuotaLimit()).toBeNull();
    fetchMock.mockResolvedValueOnce(
      jsonRes({
        headers: { "X-Quota-Limit": "40" },
        body: { analysis: {}, match_count: 10 },
      }),
    );
    await api.analyzeMatches("A", "B");
    expect(api.getQuotaLimit()).toBe(40);
    // Garbage in a later header never clobbers a good value.
    fetchMock.mockResolvedValueOnce(
      jsonRes({ headers: { "X-Quota-Limit": "banana" }, body: {} }),
    );
    await api.askMeta("q");
    expect(api.getQuotaLimit()).toBe(40);
  });
});
