export const LEVEL_COLORS = {
  calm: "#4ade80",
  warming: "#facc15",
  heated: "#fb923c",
  tilted: "#ff4655",
};

export const SEVERITY_COLORS = {
  low: "#9aa7b3",
  medium: "#facc15",
  high: "#fb923c",
  critical: "#ff4655",
};

export function playerKey(player) {
  if (!player) return "none";
  return `${player.name}#${player.tag}@${player.region}`.toLowerCase();
}

// Single source of truth for the region whitelist — the search form and the
// shareable-URL parser must agree on what a valid region is.
export const REGIONS = ["na", "eu", "ap", "kr"];

// Must match the tab ids in App.jsx's TABS.
export const TAB_IDS = ["dashboard", "analysis", "mental", "meta"];

/**
 * Parse the shareable-URL query string (?player=Name%23TAG&region=eu&tab=meta)
 * into { player: {name, tag, region} | null, tab: string | null }.
 *
 * Defensive by design: region is validated against REGIONS (bad values fall
 * back to "na"), tab against TAB_IDS (bad values are dropped), and a player
 * param without both a name and a tag is ignored entirely.
 */
export function parseShareParams(search) {
  let params;
  try {
    params = new URLSearchParams(search || "");
  } catch {
    return { player: null, tab: null };
  }

  let player = null;
  const rawPlayer = (params.get("player") || "").trim();
  if (rawPlayer.includes("#")) {
    const [head, ...rest] = rawPlayer.split("#");
    const name = head.trim();
    const tag = rest.join("#").trim();
    if (name && tag) {
      const rawRegion = (params.get("region") || "").trim().toLowerCase();
      const region = REGIONS.includes(rawRegion) ? rawRegion : "na";
      player = { name, tag, region };
    }
  }

  const rawTab = (params.get("tab") || "").trim().toLowerCase();
  const tab = TAB_IDS.includes(rawTab) ? rawTab : null;
  return { player, tab };
}

/**
 * Canonical shareable URL for the current app state. URLSearchParams handles
 * the encoding (the "#" in Name#TAG becomes %23, so it never reads as a URL
 * fragment). The default tab is omitted to keep bare links clean.
 */
export function buildShareUrl(player, tab) {
  const params = new URLSearchParams();
  if (player) {
    params.set("player", `${player.name}#${player.tag}`);
    params.set("region", player.region || "na");
  }
  if (tab && tab !== "dashboard" && TAB_IDS.includes(tab)) {
    params.set("tab", tab);
  }
  const qs = params.toString();
  return qs ? `/?${qs}` : "/";
}

const SQLITE_RE = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})$/;

const MONTHS = {
  january: 0, february: 1, march: 2, april: 3, may: 4, june: 5,
  july: 6, august: 7, september: 8, october: 9, november: 10, december: 11,
};

// Henrik's prose format after the weekday is stripped:
// "June 21, 2025 6:23 PM" (minutes and the AM/PM marker are optional-robust).
const PROSE_RE =
  /^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})(?:\s+(\d{1,2}):(\d{2})\s*([AP]M))?$/i;

export function parseDate(value) {
  if (value == null || value === "") return null;
  if (typeof value === "number") {
    return new Date(value < 1e12 ? value * 1000 : value);
  }
  const str = String(value).trim();
  // sqlite datetime('now') is UTC: "2026-07-05 01:23:45"
  const m = str.match(SQLITE_RE);
  if (m) {
    return new Date(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z`);
  }
  // Henrik's "Saturday, June 21, 2025 6:23 PM" is UTC. new Date() parsing of
  // that prose format is implementation-defined and Safari has historically
  // rejected it (iOS users would silently see raw strings), so parse it by
  // hand first and only then fall back to native parsing.
  const rest = str.replace(/^[A-Za-z]+,\s*/, "");
  const p = rest.match(PROSE_RE);
  if (p) {
    const month = MONTHS[p[1].toLowerCase()];
    if (month != null) {
      let hours = p[4] != null ? Number(p[4]) % 12 : 0;
      if ((p[6] || "").toUpperCase() === "PM") hours += 12;
      const minutes = p[5] != null ? Number(p[5]) : 0;
      return new Date(Date.UTC(Number(p[3]), month, Number(p[2]), hours, minutes));
    }
  }
  let d = new Date(`${rest} UTC`);
  if (Number.isNaN(d.getTime())) d = new Date(rest);
  return Number.isNaN(d.getTime()) ? null : d;
}

// Defensive: the backend asks Claude for plain text, but strip stray markdown
// header markers and bold pairs if they still slip through.
export function stripMarkdown(text) {
  if (typeof text !== "string") return text;
  return text
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1");
}

export function prefersReducedMotion() {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

// Break coach/answer text into readable paragraphs — never one blob.
// Splits on newlines first; very long single paragraphs get re-chunked on
// sentence boundaries.
export function splitParagraphs(text) {
  if (typeof text !== "string") return [];
  const parts = text
    .split(/\n+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const out = [];
  for (const part of parts) {
    if (part.length <= 320) {
      out.push(part);
      continue;
    }
    const sentences = part.match(/[^.!?]+[.!?]+["')\]]*\s*|[^.!?]+$/g) || [
      part,
    ];
    let buf = "";
    for (const sentence of sentences) {
      if (buf && buf.length + sentence.length > 260) {
        out.push(buf.trim());
        buf = sentence;
      } else {
        buf += sentence;
      }
    }
    if (buf.trim()) out.push(buf.trim());
  }
  return out;
}

export function relativeDate(value) {
  const d = parseDate(value);
  if (!d) return typeof value === "string" ? value : "";
  const seconds = Math.floor((Date.now() - d.getTime()) / 1000);
  if (seconds < 0) return d.toLocaleDateString();
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks}w ago`;
  return d.toLocaleDateString();
}

export function shortDateTime(value) {
  const d = parseDate(value);
  if (!d) return typeof value === "string" ? value : "";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
