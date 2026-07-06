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

const SQLITE_RE = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})$/;

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
  // Henrik's "Saturday, June 21, 2025 6:23 PM" is UTC — strip the weekday and
  // parse as UTC; if that fails fall back to local parsing, and callers fall
  // back to showing the raw string when we return null.
  const rest = str.replace(/^[A-Za-z]+,\s*/, "");
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
