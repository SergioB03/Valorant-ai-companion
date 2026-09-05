// @vitest-environment jsdom
//
// Persistence contract for the paid AI reports: reads are validated (the
// store is user-editable localStorage), writes carry a timestamp, and the
// player set is LRU-capped so the cache can't grow unbounded.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  MAX_REPORT_PLAYERS,
  isValidReportEntry,
  loadReport,
  saveReport,
} from "./reports.js";

const T0 = 1_757_000_000_000;

const analysisResult = {
  analysis: { overview: "Solid batch.", strengths: [], weaknesses: [] },
  match_count: 10,
};
const tiltResult = { tilt_score: 42, tilt_level: "warming", signals: [] };

beforeEach(() => {
  localStorage.clear();
  vi.useFakeTimers();
  vi.setSystemTime(T0);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("saveReport / loadReport round trip", () => {
  it("round-trips an analysis with the write timestamp", () => {
    saveReport("analysis", "jett#1234@na", analysisResult);
    expect(loadReport("analysis", "jett#1234@na")).toEqual({
      result: analysisResult,
      at: T0,
    });
  });

  it("round-trips a tilt report under its own key", () => {
    saveReport("tilt", "jett#1234@na", tiltResult);
    expect(loadReport("tilt", "jett#1234@na")).toEqual({
      result: tiltResult,
      at: T0,
    });
    // The two kinds don't bleed into each other.
    expect(loadReport("analysis", "jett#1234@na")).toBeNull();
  });

  it("returns null for unknown players and unknown kinds", () => {
    expect(loadReport("analysis", "nobody#1@na")).toBeNull();
    expect(loadReport("nope", "jett#1234@na")).toBeNull();
  });

  it("never reads or writes the null-player sentinel key", () => {
    saveReport("analysis", "none", analysisResult);
    expect(localStorage.length).toBe(0);
    expect(loadReport("analysis", "none")).toBeNull();
    saveReport("tilt", "", tiltResult);
    expect(localStorage.length).toBe(0);
  });
});

describe("read validation", () => {
  it("rejects corrupt JSON", () => {
    localStorage.setItem("vac:analysis:jett#1234@na", "{not json");
    expect(loadReport("analysis", "jett#1234@na")).toBeNull();
  });

  it("rejects entries with a missing or bogus timestamp", () => {
    localStorage.setItem(
      "vac:tilt:jett#1234@na",
      JSON.stringify({ result: tiltResult }),
    );
    expect(loadReport("tilt", "jett#1234@na")).toBeNull();
    localStorage.setItem(
      "vac:tilt:jett#1234@na",
      JSON.stringify({ result: tiltResult, at: "yesterday" }),
    );
    expect(loadReport("tilt", "jett#1234@na")).toBeNull();
  });

  it("rejects results of the wrong shape", () => {
    // A tilt report saved under the analysis key (and vice versa) is invalid.
    localStorage.setItem(
      "vac:analysis:jett#1234@na",
      JSON.stringify({ result: tiltResult, at: T0 }),
    );
    expect(loadReport("analysis", "jett#1234@na")).toBeNull();
    localStorage.setItem(
      "vac:tilt:jett#1234@na",
      JSON.stringify({ result: { tilt_score: "high" }, at: T0 }),
    );
    expect(loadReport("tilt", "jett#1234@na")).toBeNull();
    localStorage.setItem(
      "vac:tilt:jett#1234@na",
      JSON.stringify({ result: "a string", at: T0 }),
    );
    expect(loadReport("tilt", "jett#1234@na")).toBeNull();
  });

  it("exposes the entry validator for both kinds", () => {
    expect(isValidReportEntry("analysis", { result: analysisResult, at: T0 })).toBe(true);
    expect(isValidReportEntry("tilt", { result: tiltResult, at: T0 })).toBe(true);
    expect(isValidReportEntry("tilt", null)).toBe(false);
    expect(isValidReportEntry("tilt", { result: null, at: T0 })).toBe(false);
  });
});

describe("LRU cap across players", () => {
  function savePlayer(i) {
    vi.setSystemTime(T0 + i * 1000);
    saveReport("tilt", `p${i}#1@na`, tiltResult);
    saveReport("analysis", `p${i}#1@na`, analysisResult);
  }

  it("keeps every player up to the cap", () => {
    for (let i = 1; i <= MAX_REPORT_PLAYERS; i++) savePlayer(i);
    for (let i = 1; i <= MAX_REPORT_PLAYERS; i++) {
      expect(loadReport("tilt", `p${i}#1@na`)).not.toBeNull();
    }
  });

  it("evicts the least-recently-written player past the cap — both kinds", () => {
    for (let i = 1; i <= MAX_REPORT_PLAYERS + 1; i++) savePlayer(i);
    expect(loadReport("tilt", "p1#1@na")).toBeNull();
    expect(loadReport("analysis", "p1#1@na")).toBeNull();
    for (let i = 2; i <= MAX_REPORT_PLAYERS + 1; i++) {
      expect(loadReport("tilt", `p${i}#1@na`)).not.toBeNull();
      expect(loadReport("analysis", `p${i}#1@na`)).not.toBeNull();
    }
  });

  it("a fresh write refreshes a player's recency", () => {
    for (let i = 1; i <= MAX_REPORT_PLAYERS + 1; i++) savePlayer(i); // p1 evicted
    // Touch p2 (now the oldest survivor), then push one more player in.
    vi.setSystemTime(T0 + 100_000);
    saveReport("tilt", "p2#1@na", tiltResult);
    savePlayer(MAX_REPORT_PLAYERS + 2);
    // p3 (the actual LRU) went, refreshed p2 stayed.
    expect(loadReport("tilt", "p3#1@na")).toBeNull();
    expect(loadReport("tilt", "p2#1@na")).not.toBeNull();
  });

  it("evicts unparseable leftovers first", () => {
    localStorage.setItem("vac:tilt:corrupt#1@na", "{junk");
    for (let i = 1; i <= MAX_REPORT_PLAYERS; i++) savePlayer(i);
    // corrupt counts as a player; the write that overflows the cap drops it.
    expect(localStorage.getItem("vac:tilt:corrupt#1@na")).toBeNull();
    for (let i = 1; i <= MAX_REPORT_PLAYERS; i++) {
      expect(loadReport("tilt", `p${i}#1@na`)).not.toBeNull();
    }
  });
});

describe("storage failure tolerance", () => {
  it("saveReport never throws when storage is full or blocked", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    expect(() => saveReport("tilt", "jett#1234@na", tiltResult)).not.toThrow();
  });

  it("loadReport never throws when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    expect(loadReport("tilt", "jett#1234@na")).toBeNull();
  });
});
