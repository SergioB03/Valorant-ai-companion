import { track } from "./analytics.js";

const API = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(
  /\/+$/,
  ""
);

const enc = encodeURIComponent;

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
    throw error;
  }

  return res.json();
}

// GET /riot/account/{name}/{tag} -> { data: { puuid, region, account_level, card, name, tag, ... } }
export function getAccount(name, tag, { signal } = {}) {
  return request(`/riot/account/${enc(name)}/${enc(tag)}`, {
    endpoint: "/riot/account/{name}/{tag}",
    signal,
  });
}

// GET /riot/matches/{name}/{tag}?region&size -> [ { match_id, map, mode, started_at, agent, tier,
//   kills, deaths, assists, headshot_percent, score, won } ] (newest first)
export function getMatches(name, tag, region = "na", size = 10, { signal } = {}) {
  return request(
    `/riot/matches/${enc(name)}/${enc(tag)}?region=${enc(region)}&size=${size}`,
    { endpoint: "/riot/matches/{name}/{tag}", signal }
  );
}

// GET /claude/analyze/{name}/{tag}?region&size -> (slow)
//   { analysis: { overview, strengths[], weaknesses[], tilt_warning|null, tip },
//     match_count }
export function analyzeMatches(name, tag, region = "na", size = 10, { signal } = {}) {
  return request(
    `/claude/analyze/${enc(name)}/${enc(tag)}?region=${enc(region)}&size=${size}`,
    { endpoint: "/claude/analyze/{name}/{tag}", signal }
  );
}

// GET /mental/tilt-check/{name}/{tag}?region&size -> TiltReport (includes coach_message)
export function tiltCheck(name, tag, region = "na", size = 10, { signal } = {}) {
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
  return request(`/meta/ask`, {
    endpoint: "/meta/ask",
    signal,
    method: "POST",
    body: JSON.stringify({ question }),
  });
}
