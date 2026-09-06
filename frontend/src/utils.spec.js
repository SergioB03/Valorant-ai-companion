import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  DEMO_PLAYER,
  PROMPTED_TILT_CAP,
  RECENT_PLAYERS_MAX,
  addRecentPlayer,
  buildShareUrl,
  bumpPromptedChecks,
  isDemoPlayer,
  parseDate,
  parseRecentPlayers,
  parseShareParams,
  parseStoredPlayer,
  promptedChecksToday,
  resolveInitialPlayer,
  splitParagraphs,
  stripMarkdown,
  tiltRitualCopy,
  utcDayKey,
} from "./utils.js";

describe("parseDate", () => {
  it("parses sqlite UTC datetimes", () => {
    const d = parseDate("2026-07-05 01:23:45");
    expect(d.getTime()).toBe(Date.UTC(2026, 6, 5, 1, 23, 45));
  });

  it("parses sqlite T-separated datetimes", () => {
    const d = parseDate("2026-07-05T01:23:45");
    expect(d.getTime()).toBe(Date.UTC(2026, 6, 5, 1, 23, 45));
  });

  // The Safari case: Henrik's prose format is implementation-defined for
  // new Date() and Safari has historically rejected it. The manual prose
  // parser must handle it without ever reaching native parsing.
  it("parses Henrik's prose format (weekday, PM) as UTC", () => {
    const d = parseDate("Saturday, June 21, 2025 6:23 PM");
    expect(d.getTime()).toBe(Date.UTC(2025, 5, 21, 18, 23));
  });

  it("parses the prose format without a weekday", () => {
    const d = parseDate("June 21, 2025 6:23 PM");
    expect(d.getTime()).toBe(Date.UTC(2025, 5, 21, 18, 23));
  });

  it("handles 12 AM and 12 PM correctly", () => {
    expect(parseDate("Monday, January 5, 2026 12:15 AM").getTime()).toBe(
      Date.UTC(2026, 0, 5, 0, 15),
    );
    expect(parseDate("Monday, January 5, 2026 12:15 PM").getTime()).toBe(
      Date.UTC(2026, 0, 5, 12, 15),
    );
  });

  it("parses a date-only prose string as UTC midnight", () => {
    const d = parseDate("June 21, 2025");
    expect(d.getTime()).toBe(Date.UTC(2025, 5, 21, 0, 0));
  });

  it("treats numbers as unix seconds or milliseconds", () => {
    expect(parseDate(1750000000).getTime()).toBe(1750000000 * 1000);
    expect(parseDate(1750000000000).getTime()).toBe(1750000000000);
  });

  it("returns null for empty and unparseable input", () => {
    expect(parseDate(null)).toBeNull();
    expect(parseDate("")).toBeNull();
    expect(parseDate("not a date")).toBeNull();
  });
});

describe("stripMarkdown", () => {
  it("strips heading markers and bold pairs", () => {
    expect(stripMarkdown("## The read\n**Aim** is fine")).toBe(
      "The read\nAim is fine",
    );
  });

  it("passes non-strings through untouched", () => {
    expect(stripMarkdown(null)).toBeNull();
    expect(stripMarkdown(42)).toBe(42);
  });
});

describe("parseShareParams", () => {
  it("parses a full share URL", () => {
    const { player, tab } = parseShareParams(
      "?player=Boaster%23123&region=eu&tab=analysis",
    );
    expect(player).toEqual({ name: "Boaster", tag: "123", region: "eu" });
    expect(tab).toBe("analysis");
  });

  it("falls back to na for an invalid region", () => {
    const { player } = parseShareParams("?player=A%23B&region=mars");
    expect(player.region).toBe("na");
  });

  it("normalizes region case", () => {
    const { player } = parseShareParams("?player=A%23B&region=EU");
    expect(player.region).toBe("eu");
  });

  it("drops an unknown tab", () => {
    expect(parseShareParams("?tab=admin").tab).toBeNull();
  });

  it("ignores a player without both name and tag", () => {
    expect(parseShareParams("?player=OnlyName").player).toBeNull();
    expect(parseShareParams("?player=%23onlytag").player).toBeNull();
    expect(parseShareParams("?player=Name%23").player).toBeNull();
  });

  it("keeps extra hashes inside the tag", () => {
    const { player } = parseShareParams("?player=A%23B%23C");
    expect(player).toEqual({ name: "A", tag: "B#C", region: "na" });
  });

  it("returns nulls for empty input", () => {
    expect(parseShareParams("")).toEqual({ player: null, tab: null });
    expect(parseShareParams(undefined)).toEqual({ player: null, tab: null });
  });
});

describe("buildShareUrl", () => {
  it("returns the bare root with nothing to share", () => {
    expect(buildShareUrl(null, "dashboard")).toBe("/");
    expect(buildShareUrl(null, null)).toBe("/");
  });

  it("omits the default tab", () => {
    const url = buildShareUrl({ name: "A", tag: "B", region: "na" }, "dashboard");
    expect(url).not.toContain("tab=");
  });

  it("round-trips through parseShareParams, including spaces and #", () => {
    const player = { name: "Jett Main", tag: "NA1", region: "ap" };
    const url = buildShareUrl(player, "meta");
    const parsed = parseShareParams(new URL(`https://x.test${url}`).search);
    expect(parsed.player).toEqual(player);
    expect(parsed.tab).toBe("meta");
  });

  it("percent-encodes the # so it never reads as a fragment", () => {
    const url = buildShareUrl({ name: "A", tag: "B", region: "na" }, null);
    expect(url).not.toContain("#");
    expect(url).toContain("%23");
  });
});

describe("addRecentPlayer", () => {
  const jett = { name: "Jett", tag: "1234", region: "eu" };

  it("unshifts the newest player", () => {
    const list = addRecentPlayer([{ name: "Sage", tag: "1", region: "na" }], jett);
    expect(list.map((p) => p.name)).toEqual(["Jett", "Sage"]);
  });

  it("dedupes by playerKey and moves the hit to the front", () => {
    const start = [
      { name: "Sage", tag: "1", region: "na" },
      { name: "Jett", tag: "1234", region: "eu" },
    ];
    const list = addRecentPlayer(start, jett);
    expect(list).toHaveLength(2);
    expect(list[0].name).toBe("Jett");
  });

  it("dedupe is case-insensitive but region-aware", () => {
    const start = [{ name: "JETT", tag: "1234", region: "eu" }];
    expect(addRecentPlayer(start, jett)).toHaveLength(1);
    // Same Riot ID on another region is a distinct entry.
    expect(
      addRecentPlayer(start, { ...jett, region: "na" }),
    ).toHaveLength(2);
  });

  it("caps the list", () => {
    let list = [];
    for (let i = 0; i < RECENT_PLAYERS_MAX + 3; i++) {
      list = addRecentPlayer(list, { name: `P${i}`, tag: "1", region: "na" });
    }
    expect(list).toHaveLength(RECENT_PLAYERS_MAX);
    // Newest first; the oldest fell off the end.
    expect(list[0].name).toBe(`P${RECENT_PLAYERS_MAX + 2}`);
  });

  it("ignores invalid players and tolerates a non-array list", () => {
    const start = [jett];
    expect(addRecentPlayer(start, null)).toBe(start);
    expect(addRecentPlayer(start, { name: "NoTag" })).toBe(start);
    expect(addRecentPlayer(start, { name: "  ", tag: "1" })).toBe(start);
    expect(addRecentPlayer("garbage", jett)).toEqual([jett]);
  });

  it("normalizes an unknown region to na", () => {
    const [p] = addRecentPlayer([], { name: "A", tag: "B", region: "mars" });
    expect(p.region).toBe("na");
  });
});

describe("parseRecentPlayers", () => {
  it("parses a valid stored list", () => {
    const raw = JSON.stringify([
      { name: "Jett", tag: "1234", region: "eu" },
      { name: "Sage", tag: "1", region: "na" },
    ]);
    expect(parseRecentPlayers(raw)).toEqual([
      { name: "Jett", tag: "1234", region: "eu" },
      { name: "Sage", tag: "1", region: "na" },
    ]);
  });

  it("drops invalid entries and defaults bad regions — like loadSavedPlayer", () => {
    const raw = JSON.stringify([
      { name: "Jett", tag: "1234", region: "mars" },
      { name: "", tag: "1" },
      { tag: "no-name" },
      "not an object",
      null,
    ]);
    expect(parseRecentPlayers(raw)).toEqual([
      { name: "Jett", tag: "1234", region: "na" },
    ]);
  });

  it("dedupes tampered duplicates on read", () => {
    const raw = JSON.stringify([
      { name: "Jett", tag: "1234", region: "eu" },
      { name: "JETT", tag: "1234", region: "eu" },
    ]);
    expect(parseRecentPlayers(raw)).toHaveLength(1);
  });

  it("caps an oversized stored list on read", () => {
    const raw = JSON.stringify(
      Array.from({ length: 20 }, (_, i) => ({
        name: `P${i}`,
        tag: "1",
        region: "na",
      })),
    );
    expect(parseRecentPlayers(raw)).toHaveLength(RECENT_PLAYERS_MAX);
  });

  it("returns [] for corrupt JSON, non-arrays and null", () => {
    expect(parseRecentPlayers("{oops")).toEqual([]);
    expect(parseRecentPlayers('{"name":"Jett"}')).toEqual([]);
    expect(parseRecentPlayers(null)).toEqual([]);
    expect(parseRecentPlayers(undefined)).toEqual([]);
  });
});

describe("resolveInitialPlayer — the landing routing decision", () => {
  const url = { name: "Boaster", tag: "123", region: "eu" };
  const session = JSON.stringify({ name: "Jett", tag: "1234", region: "na" });

  it("URL player wins over the session marker", () => {
    expect(resolveInitialPlayer(url, session)).toEqual({
      player: url,
      source: "url",
    });
  });

  it("falls back to the session marker when there is no URL player", () => {
    expect(resolveInitialPlayer(null, session)).toEqual({
      player: { name: "Jett", tag: "1234", region: "na" },
      source: "active",
    });
  });

  it("lands (null player) when neither exists — never reads vac:last-player", () => {
    expect(resolveInitialPlayer(null, null)).toEqual({
      player: null,
      source: null,
    });
  });

  it("treats a corrupt or junk session marker as absent", () => {
    expect(resolveInitialPlayer(null, "{oops").player).toBeNull();
    expect(resolveInitialPlayer(null, '"a string"').player).toBeNull();
    expect(resolveInitialPlayer(null, '{"name":"NoTag"}').player).toBeNull();
  });

  it("rejects the demo sentinel from both inputs (tampered storage, leaked URL)", () => {
    const demoRaw = JSON.stringify(DEMO_PLAYER);
    expect(resolveInitialPlayer(null, demoRaw).player).toBeNull();
    expect(resolveInitialPlayer({ ...DEMO_PLAYER }, null).player).toBeNull();
  });

  it("normalizes an unknown region in the session marker", () => {
    const raw = JSON.stringify({ name: "A", tag: "B", region: "mars" });
    expect(resolveInitialPlayer(null, raw).player.region).toBe("na");
  });
});

describe("parseStoredPlayer", () => {
  it("round-trips a valid player", () => {
    const raw = JSON.stringify({ name: "Sage", tag: "1", region: "ap" });
    expect(parseStoredPlayer(raw)).toEqual({ name: "Sage", tag: "1", region: "ap" });
  });

  it("returns null for empty, corrupt and demo values", () => {
    expect(parseStoredPlayer(null)).toBeNull();
    expect(parseStoredPlayer("")).toBeNull();
    expect(parseStoredPlayer("{bad")).toBeNull();
    expect(parseStoredPlayer(JSON.stringify(DEMO_PLAYER))).toBeNull();
  });
});

describe("demo sentinel exclusion", () => {
  it("isDemoPlayer matches case-insensitively via playerKey", () => {
    expect(isDemoPlayer({ name: "demo", tag: "vac", region: "na" })).toBe(true);
    expect(isDemoPlayer({ name: "Demo", tag: "VAC1", region: "na" })).toBe(false);
    expect(isDemoPlayer(null)).toBe(false);
  });

  it("never enters the recents list — add or parse", () => {
    expect(addRecentPlayer([], { ...DEMO_PLAYER })).toEqual([]);
    const raw = JSON.stringify([
      DEMO_PLAYER,
      { name: "Jett", tag: "1234", region: "eu" },
    ]);
    expect(parseRecentPlayers(raw)).toEqual([
      { name: "Jett", tag: "1234", region: "eu" },
    ]);
  });
});

describe("tilt ritual copy + prompted-check soft cap", () => {
  const NOW = Date.UTC(2026, 8, 5, 20, 0, 0);

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("invites a first check when there is no timestamp", () => {
    expect(tiltRitualCopy(null, NOW)).toMatch(/first tilt check/);
    expect(tiltRitualCopy(Number.NaN, NOW)).toMatch(/first tilt check/);
  });

  it("varies the copy by how long ago the last check was", () => {
    const h = 3_600_000;
    expect(tiltRitualCopy(NOW - 2 * h, NOW)).toMatch(/back for another queue/);
    expect(tiltRitualCopy(NOW - 24 * h, NOW)).toMatch(/see where your mental's at/);
    expect(tiltRitualCopy(NOW - 100 * h, NOW)).toMatch(/Been a while/);
  });

  it("utcDayKey buckets by UTC date", () => {
    expect(utcDayKey(NOW)).toBe("2026-09-05");
  });

  it("counts, bumps and resets the prompted-check counter by day", () => {
    const day = utcDayKey(NOW);
    expect(promptedChecksToday(null, day)).toBe(0);
    expect(promptedChecksToday("{junk", day)).toBe(0);
    let raw = bumpPromptedChecks(null, day);
    raw = bumpPromptedChecks(raw, day);
    expect(promptedChecksToday(raw, day)).toBe(2);
    // Yesterday's counter does not carry into today.
    expect(promptedChecksToday(raw, "2026-09-06")).toBe(0);
    // The cap constant is what the landing checks against.
    expect(PROMPTED_TILT_CAP).toBeGreaterThan(0);
  });
});

describe("splitParagraphs", () => {
  it("splits on newlines and drops blanks", () => {
    expect(splitParagraphs("one\n\ntwo\nthree")).toEqual([
      "one",
      "two",
      "three",
    ]);
  });

  it("re-chunks very long single paragraphs on sentence boundaries", () => {
    const sentence = "This is a fairly long sentence about crosshair placement. ";
    const blob = sentence.repeat(10).trim();
    const parts = splitParagraphs(blob);
    expect(parts.length).toBeGreaterThan(1);
    expect(parts.join(" ")).toContain("crosshair placement");
  });

  it("returns [] for non-strings", () => {
    expect(splitParagraphs(null)).toEqual([]);
    expect(splitParagraphs(undefined)).toEqual([]);
  });
});
