import { describe, expect, it } from "vitest";
import {
  buildShareUrl,
  parseDate,
  parseShareParams,
  splitParagraphs,
  stripMarkdown,
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
