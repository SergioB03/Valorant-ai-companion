import { track } from "./analytics.js";

const API = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(
  /\/+$/,
  ""
);

const enc = encodeURIComponent;

// ---------- Demo mode (Wave 2) ----------
// A module-level flag short-circuits EVERY endpoint below against the
// dynamically-imported fixtures module, so the demo player can never reach
// the network. This matters beyond politeness: /mental/coach swallows a
// failed Henrik lookup and still calls Claude, so a demo identity falling
// through to a real request would spend real money (verified in
// docs/GROWTH-FEATURES.md). The fixtures module stays out of the main bundle
// until the demo actually starts.

let demoMode = false;

export function setDemoMode(on) {
  demoMode = Boolean(on);
}

export function isDemoMode() {
  return demoMode;
}

function demoFixtures() {
  return import("./demo-fixtures.js");
}

// ---------- Daily AI quota (Wave 2) ----------
// The backend carries the configured daily limit in X-Quota-Limit on every
// AI response (success or 429). Remember the last-seen value so the "uses 1
// of your N free AI actions" captions never hardcode a number.

let lastQuotaLimit = null;

export function getQuotaLimit() {
  return lastQuotaLimit;
}

// Matched to the reverse proxy's 60s window — a longer client timeout would
// never fire before the proxy 504s anyway.
const TIMEOUT_MS = 60_000;

// Combine the deadline with an optional caller-supplied cancel signal.
// AbortSignal.any/timeout are baseline in every browser this app supports;
// the guards only cover very old engines, where requests simply lose the
// timeout rather than breaking.
function requestSignal(signal) {
  const signals = [];
  if (signal) signals.push(signal);
  if (typeof AbortSignal !== "undefined" && AbortSignal.timeout) {
    signals.push(AbortSignal.timeout(TIMEOUT_MS));
  }
  if (signals.length === 0) return undefined;
  if (signals.length === 1 || !AbortSignal.any) return signals[0];
  return AbortSignal.any(signals);
}

/** True when a request failed because the caller cancelled it (Cancel button,
 *  unmount, player switch) — callers surface this as a gentle "cancelled"
 *  state instead of an error banner. */
export function isCancelled(err) {
  return Boolean(err && err.cancelled);
}

// `endpoint` is the path template only (e.g. "/riot/account/{name}/{tag}") so
// api_error events never carry riot names/tags. Never fall back to `path`.
// `signal` is an optional caller AbortSignal; every request also gets a 60s
// deadline so a stalled upstream can never brick a button forever.
async function request(path, { endpoint, signal, ...options } = {}) {
  let res;
  try {
    res = await fetch(`${API}${path}`, {
      ...options,
      signal: requestSignal(signal),
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
  } catch (err) {
    // fetch rejects with the abort reason: TimeoutError for the deadline,
    // AbortError for a caller cancel. Cancels are not api_error events —
    // the user asked for them.
    if (err && err.name === "AbortError") {
      const cancelled = new Error("Request cancelled.");
      cancelled.cancelled = true;
      throw cancelled;
    }
    if (err && err.name === "TimeoutError") {
      track("api_error", { endpoint: endpoint || "unknown", status: 0, timeout: true });
      throw new Error(
        "The request timed out after a minute — the server may be busy. Try again."
      );
    }
    track("api_error", { endpoint: endpoint || "unknown", status: 0 });
    throw new Error(
      "Could not reach the backend. Make sure the API server is running."
    );
  }

  // The daily-quota limit rides along on AI responses — successes and 429s
  // alike. Remember it for the static captions near the AI buttons.
  const limitHeader = res.headers.get("X-Quota-Limit");
  if (limitHeader != null) {
    const limit = parseInt(limitHeader, 10);
    if (Number.isFinite(limit) && limit > 0) lastQuotaLimit = limit;
  }

  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    try {
      const body = await res.json();
      if (body && body.detail) {
        detail =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
      }
    } catch {
      /* body was not JSON — keep the generic message */
    }
    track("api_error", { endpoint: endpoint || "unknown", status: res.status });
    const error = new Error(detail);
    error.status = res.status;
    // Daily quota exhaustion is keyed ONLY on this header — three different
    // 429s exist (daily quota, per-minute slowapi, Henrik upstream), so a
    // bare status check would show "resets at midnight" for the wrong ones.
    error.quotaExhausted = res.headers.get("X-Quota-Exhausted") === "1";
    const retryAfter = parseInt(res.headers.get("Retry-After") || "", 10);
    if (Number.isFinite(retryAfter) && retryAfter >= 0) {
      error.retryAfterSeconds = retryAfter;
    }
    throw error;
  }

  return res.json();
}

// GET /riot/account/{name}/{tag} -> { data: { puuid, region, account_level, card, name, tag, ... } }
export function getAccount(name, tag, { signal } = {}) {
  if (demoMode) return demoFixtures().then((f) => f.demoAccount());
  return request(`/riot/account/${enc(name)}/${enc(tag)}`, {
    endpoint: "/riot/account/{name}/{tag}",
    signal,
  });
}

// GET /riot/matches/{name}/{tag}?region&size -> [ { match_id, map, mode, started_at, agent, tier,
//   kills, deaths, assists, headshot_percent, score, won } ] (newest first)
export function getMatches(name, tag, region = "na", size = 10, { signal } = {}) {
  if (demoMode) return demoFixtures().then((f) => f.demoMatches(size));
  return request(
    `/riot/matches/${enc(name)}/${enc(tag)}?region=${enc(region)}&size=${size}`,
    { endpoint: "/riot/matches/{name}/{tag}", signal }
  );
}

// GET /claude/analyze/{name}/{tag}?region&size -> (slow)
//   { analysis: { overview, strengths[], weaknesses[], tilt_warning|null, tip },
//     match_count }
export function analyzeMatches(name, tag, region = "na", size = 10, { signal } = {}) {
  if (demoMode) return demoFixtures().then((f) => f.demoAnalysis());
  return request(
    `/claude/analyze/${enc(name)}/${enc(tag)}?region=${enc(region)}&size=${size}`,
    { endpoint: "/claude/analyze/{name}/{tag}", signal }
  );
}

// GET /mental/tilt-check/{name}/{tag}?region&size -> TiltReport (includes coach_message)
export function tiltCheck(name, tag, region = "na", size = 10, { signal } = {}) {
  if (demoMode) return demoFixtures().then((f) => f.demoTiltReport());
  return request(
    `/mental/tilt-check/${enc(name)}/${enc(tag)}?region=${enc(region)}&size=${size}`,
    { endpoint: "/mental/tilt-check/{name}/{tag}", signal }
  );
}

// POST /mental/coach { game_name, tag_line, region, message, history }
//   -> { reply, tilt_score, tilt_level }
// `history` carries this browser's own conversation so the coach has context.
// The server does not store or replay conversation text — sending it from here
// keeps a chat scoped to the person having it rather than to the Riot ID they
// happened to search.
export function coachChat(name, tag, region, message, history = [], { signal } = {}) {
  // Defensive: the demo UI disables the chat input entirely, but even a
  // programmatic call must never reach /mental/coach (it spends Claude money
  // even when the player lookup fails).
  if (demoMode) return demoFixtures().then((f) => f.demoCoachReply());
  return request(`/mental/coach`, {
    endpoint: "/mental/coach",
    signal,
    method: "POST",
    body: JSON.stringify({
      game_name: name,
      tag_line: tag,
      region,
      message,
      history: history
        .slice(-10)
        .map((m) => ({ role: m.role, text: String(m.text).slice(0, 2000) })),
    }),
  });
}

// GET /mental/profile/{name}/{tag} -> { riot_id, snapshots, sessions, trend }
export function getMentalProfile(name, tag, { signal } = {}) {
  if (demoMode) return demoFixtures().then((f) => f.demoProfile());
  return request(`/mental/profile/${enc(name)}/${enc(tag)}`, {
    endpoint: "/mental/profile/{name}/{tag}",
    signal,
  });
}

// POST /meta/ask { question } -> (503 when RAG is unavailable)
//   { answer, sources: [{source, section, snippet, used?}], corpus_vintage? }
// `used` and `corpus_vintage` are optional additions — older backends omit
// them and the UI degrades gracefully.
export function askMeta(question, { signal } = {}) {
  if (demoMode) return demoFixtures().then((f) => f.demoMetaAnswer());
  return request(`/meta/ask`, {
    endpoint: "/meta/ask",
    signal,
    method: "POST",
    body: JSON.stringify({ question }),
  });
}
