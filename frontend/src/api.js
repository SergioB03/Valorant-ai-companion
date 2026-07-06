const API = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(
  /\/+$/,
  ""
);

const enc = encodeURIComponent;

async function request(path, options = {}) {
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
    const error = new Error(detail);
    error.status = res.status;
    throw error;
  }

  return res.json();
}

// GET /riot/account/{name}/{tag} -> { data: { puuid, region, account_level, card, name, tag, ... } }
export function getAccount(name, tag) {
  return request(`/riot/account/${enc(name)}/${enc(tag)}`);
}

// GET /riot/matches/{name}/{tag}?region&size -> [ { match_id, map, mode, started_at, agent, tier,
//   kills, deaths, assists, headshot_percent, score, won } ] (newest first)
export function getMatches(name, tag, region = "na", size = 10) {
  return request(
    `/riot/matches/${enc(name)}/${enc(tag)}?region=${enc(region)}&size=${size}`
  );
}

// GET /claude/analyze/{name}/{tag}?region&size -> { analysis, match_count } (slow)
export function analyzeMatches(name, tag, region = "na", size = 10) {
  return request(
    `/claude/analyze/${enc(name)}/${enc(tag)}?region=${enc(region)}&size=${size}`
  );
}

// GET /mental/tilt-check/{name}/{tag}?region&size -> TiltReport (includes coach_message)
export function tiltCheck(name, tag, region = "na", size = 10) {
  return request(
    `/mental/tilt-check/${enc(name)}/${enc(tag)}?region=${enc(region)}&size=${size}`
  );
}

// POST /mental/coach { game_name, tag_line, region, message } -> { reply, tilt_score, tilt_level }
export function coachChat(name, tag, region, message) {
  return request(`/mental/coach`, {
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
  return request(`/mental/profile/${enc(name)}/${enc(tag)}`);
}

// POST /meta/ask { question } -> { answer, sources } (503 when RAG is unavailable)
export function askMeta(question) {
  return request(`/meta/ask`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}
