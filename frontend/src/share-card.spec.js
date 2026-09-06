// The tilt card draws user strings with ctx.fillText only (no HTML/SVG
// templating), so the one text-safety job left is sanitization: strip
// control/bidi/zero-width characters and cap the length so a hostile "name"
// can't wreck the layout or smuggle direction overrides into a shared image.
import { describe, expect, it } from "vitest";
import { NAME_MAX, sanitizeCardName } from "./share-card.js";

describe("sanitizeCardName", () => {
  it("passes normal Riot names through untouched", () => {
    expect(sanitizeCardName("Jett Main")).toBe("Jett Main");
    expect(sanitizeCardName("xX_Reyna_Xx")).toBe("xX_Reyna_Xx");
  });

  it("strips control characters and collapses whitespace", () => {
    expect(sanitizeCardName("Je\u0000tt\u0007")).toBe("Jett");
    expect(sanitizeCardName("  spaced \t\n out  ")).toBe("spaced out");
  });

  it("strips bidi overrides and zero-width characters", () => {
    expect(sanitizeCardName("abc\u202edef\u200b")).toBe("abcdef");
    expect(sanitizeCardName("\u2066iso\u2069late")).toBe("isolate");
    expect(sanitizeCardName("\ufeffbom")).toBe("bom");
  });

  it("caps the length with an ellipsis", () => {
    const long = "A".repeat(60);
    const out = sanitizeCardName(long);
    expect(out.length).toBeLessThanOrEqual(NAME_MAX);
    expect(out.endsWith("…")).toBe(true);
  });

  it("respects a custom cap (tags are shorter)", () => {
    expect(sanitizeCardName("VERYLONGTAG", 8)).toBe("VERYLON…");
  });

  it("falls back to a placeholder when nothing printable is left", () => {
    expect(sanitizeCardName("")).toBe("Player");
    expect(sanitizeCardName("\u200b\u202e")).toBe("Player");
    expect(sanitizeCardName(null)).toBe("Player");
    expect(sanitizeCardName(undefined)).toBe("Player");
  });
});
