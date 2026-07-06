import { track } from "./analytics.js";

const API = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(
  /\/+$/,
  ""
);

const enc = encodeURIComponent;

// `endpoint` is the path template only (e.g. "/riot/account/{name}/{tag}") so
// api_error events never carry riot names/tags. Never fall back to `path`.
async function request(path, { endpoint, ...options } = {}) {
  let res;
  try {
    res = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
  } catch (err) {
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
export function getAccount(name, tag) {
  return request(`/riot/account/${enc(name)}/${enc(tag)}`, {
    endpoint: "/riot/account/{name}/{tag}",
  });
}

// GET /riot/matches/{name}/{tag}?region&size -> [ { match_id, map, mode, started_at, agent, tier,
//   kills, deaths, assists, headshot_percent, score, won } ] (newest first)
export function getMatches(name, tag, region = "na", size = 10) {
  return request(
    `/riot/matches/${enc(name)}/${enc(tag)}?region=${enc(region)}&size=${size}`,
    { endpoint: "/riot/matches/{name}/{tag}" }
  );
}

// GET /claude/analyze/{name}/{tag}?region&size -> (slow)
//   { analysis: { overview, strengths[], weaknesses[], tilt_warning|null, tip },
//     match_count }
export function analyzeMatches(name, tag, region = "na", size = 10) {
  return request(
    `/claude/analyze/${enc(name)}/${enc(tag)}?region=${enc(region)}&size=${size}`,
    { endpoint: "/claude/analyze/{name}/{tag}" }
  );
}

// GET /mental/tilt-check/{name}/{tag}?region&size -> TiltReport (includes coach_message)
export function tiltCheck(name, tag, region = "na", size = 10) {
  return request(
    `/mental/tilt-check/${enc(name)}/${enc(tag)}?region=${enc(region)}&size=${size}`,
    { endpoint: "/mental/tilt-check/{name}/{tag}" }
  );
}

// POST /mental/coach { game_name, tag_line, region, message } -> { reply, tilt_score, tilt_level }
export function coachChat(name, tag, region, message) {
  return request(`/mental/coach`, {
    endpoint: "/mental/coach",
    method: "POST",
    body: JSON.stringify({
      game_name: name,
      tag_line: tag,
      region,
      message,
    }),
  });
}

// GET /mental/profile/{name}/{tag} -> { riot_id, snapshots, sessions, trend }
export function getMentalProfile(name, tag) {
  return request(`/mental/profile/${enc(name)}/${enc(tag)}`, {
    endpoint: "/mental/profile/{name}/{tag}",
  });
}

// POST /meta/ask { question } -> { answer, sources } (503 when RAG is unavailable)
export function askMeta(question) {
  return request(`/meta/ask`, {
    endpoint: "/meta/ask",
    method: "POST",
    body: JSON.stringify({ question }),
  });
}
