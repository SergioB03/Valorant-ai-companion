// Shareable tilt-card PNG (Wave 2), rendered entirely on a <canvas> with
// ctx.fillText — deliberately NO SVG-in-<img> intermediate (custom fonts
// silently fall back inside SVG images) and no HTML/SVG templating of user
// strings (names never touch a parser, so there is no injection surface).
// Visual language transposed from scripts/make-og-card.mjs. App branding
// only — no Riot marks.

import { LEVEL_COLORS } from "./utils.js";

const W = 1200;
const H = 630;

const BG_TOP = "#16222e";
const BG_BOTTOM = "#0f1923";
const TEXT = "#ece8e1";
const MUTED = "#9aa7b3";
const ACCENT = "#ff4655";
const BORDER = "#2c3944";

const DISPLAY_STACK = '"Bebas Neue","Arial Narrow",Impact,sans-serif';
const BODY_STACK = '"Inter","Segoe UI",ui-sans-serif,system-ui,sans-serif';

export const NAME_MAX = 20;
export const TAG_MAX = 8;

/**
 * Sanitize a Riot name/tag for drawing: strip control, bidi-override and
 * zero-width characters, collapse whitespace, and cap the length (canvas
 * ignores markup, but a 200-char "name" would still wreck the layout).
 * Exported for tests.
 */
export function sanitizeCardName(value, max = NAME_MAX) {
  const cleaned = String(value ?? "")
    // C0/C1 controls, DEL, zero-widths, bidi overrides and isolates.
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return "Player";
  if (cleaned.length <= max) return cleaned;
  return `${cleaned.slice(0, Math.max(1, max - 1)).trimEnd()}…`;
}

// The app's V mark, same path as the header logo / OG card (32x32 units).
const LOGO_PATH = "M4 7l11 14h6L8 7H4zm24 0h-6l-7 9 3 4L28 7z";

async function ensureFonts() {
  // fillText only uses a webfont that is already loaded; ask for the exact
  // faces first. Any failure (offline, no Font Loading API) just means the
  // fallback stacks draw instead — never a broken card.
  try {
    if (typeof document !== "undefined" && document.fonts && document.fonts.load) {
      await Promise.all([
        document.fonts.load(`italic 76px ${DISPLAY_STACK}`),
        document.fonts.load(`italic 190px ${DISPLAY_STACK}`),
        document.fonts.load(`600 30px ${BODY_STACK}`),
      ]);
    }
  } catch {
    /* fall back to system faces */
  }
}

/**
 * Render the first-person tilt card. Returns the finished canvas.
 * `report` needs tilt_score / tilt_level / recommendation; `player` a
 * name/tag pair (sanitized and capped here, never trusted).
 */
export async function renderTiltCard(player, report, now = new Date()) {
  await ensureFonts();

  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");

  const score = Math.max(0, Math.min(100, Number(report?.tilt_score) || 0));
  const level = String(report?.tilt_level || "unknown");
  const color = LEVEL_COLORS[level] || MUTED;
  const name = sanitizeCardName(player?.name, NAME_MAX);
  const tag = sanitizeCardName(player?.tag, TAG_MAX);

  // Background
  const bg = ctx.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, BG_TOP);
  bg.addColorStop(1, BG_BOTTOM);
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  // Top accent glow bar
  const glow = ctx.createLinearGradient(0, 0, W, 0);
  glow.addColorStop(0, "rgba(255,70,85,0)");
  glow.addColorStop(0.3, ACCENT);
  glow.addColorStop(0.7, ACCENT);
  glow.addColorStop(1, "rgba(255,70,85,0)");
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, W, 6);

  // Faint angled corner panels, echoing the app's cut-corner design
  ctx.fillStyle = "rgba(255,70,85,0.06)";
  ctx.beginPath();
  ctx.moveTo(0, H);
  ctx.lineTo(340, H);
  ctx.lineTo(420, H - 80);
  ctx.lineTo(0, H - 80);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = "rgba(125,211,252,0.05)";
  ctx.beginPath();
  ctx.moveTo(W, 0);
  ctx.lineTo(W - 300, 0);
  ctx.lineTo(W - 380, 90);
  ctx.lineTo(W, 90);
  ctx.closePath();
  ctx.fill();

  // Logo + brand line
  ctx.save();
  ctx.translate(84, 64);
  ctx.scale(2.2, 2.2);
  ctx.fillStyle = ACCENT;
  if (typeof Path2D !== "undefined") {
    ctx.fill(new Path2D(LOGO_PATH));
  }
  ctx.restore();
  ctx.fillStyle = MUTED;
  ctx.font = `italic 34px ${DISPLAY_STACK}`;
  ctx.fillText("VALORANT AI COMPANION", 176, 118);

  // First-person title + player line
  ctx.fillStyle = TEXT;
  ctx.font = `italic 76px ${DISPLAY_STACK}`;
  ctx.fillText("MY TILT CHECK", 84, 246);
  ctx.font = `600 30px ${BODY_STACK}`;
  ctx.fillStyle = TEXT;
  const nameText = name;
  ctx.fillText(nameText, 86, 296);
  const nameWidth = ctx.measureText(nameText).width;
  ctx.fillStyle = MUTED;
  ctx.fillText(`#${tag}`, 86 + nameWidth + 8, 296);

  // Big score + level chip (right side)
  ctx.fillStyle = color;
  ctx.font = `italic 190px ${DISPLAY_STACK}`;
  ctx.textAlign = "right";
  ctx.fillText(String(score), W - 210, 300);
  ctx.textAlign = "left";
  ctx.font = `600 26px ${BODY_STACK}`;
  const levelText = level.toUpperCase();
  const levelWidth = ctx.measureText(levelText).width;
  const chipX = W - 210 + 24;
  const chipY = 254;
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.strokeRect(chipX, chipY, levelWidth + 36, 52);
  ctx.fillStyle = color;
  ctx.fillText(levelText, chipX + 18, chipY + 36);
  ctx.fillStyle = MUTED;
  ctx.font = `500 22px ${BODY_STACK}`;
  ctx.fillText("/ 100", chipX, 224);

  // Meter track + fill + ticks
  const meterX = 84;
  const meterY = 366;
  const meterW = W - 168;
  const meterH = 26;
  ctx.fillStyle = "#0d151d";
  ctx.fillRect(meterX, meterY, meterW, meterH);
  ctx.strokeStyle = BORDER;
  ctx.lineWidth = 2;
  ctx.strokeRect(meterX, meterY, meterW, meterH);
  ctx.fillStyle = color;
  ctx.fillRect(meterX + 2, meterY + 2, Math.round((meterW - 4) * (score / 100)), meterH - 4);
  ctx.fillStyle = "rgba(236,232,225,0.3)";
  for (const t of [25, 50, 75]) {
    ctx.fillRect(meterX + Math.round(meterW * (t / 100)), meterY, 2, meterH);
  }
  ctx.fillStyle = MUTED;
  ctx.font = `600 20px ${BODY_STACK}`;
  ctx.fillText("CALM", meterX, meterY + 62);
  ctx.textAlign = "right";
  ctx.fillText("TILTED", meterX + meterW, meterY + 62);
  ctx.textAlign = "left";

  // Recommendation (already short, backend-fixed strings; capped anyway)
  const rec = sanitizeCardName(report?.recommendation, 80);
  if (rec && rec !== "Player") {
    ctx.fillStyle = TEXT;
    ctx.font = `600 30px ${BODY_STACK}`;
    ctx.fillText(rec, 84, 508);
  }

  // Footer: honest provenance + date
  const date = now.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
  ctx.fillStyle = MUTED;
  ctx.font = `500 22px ${BODY_STACK}`;
  ctx.fillText(`AI estimate from public match data — rebuy.gg · ${date}`, 84, 574);

  return canvas;
}

/** canvas.toBlob as a Promise. */
export function cardBlob(canvas) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("Could not encode the card image."));
    }, "image/png");
  });
}
