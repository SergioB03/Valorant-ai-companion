// Persist the paid AI reports (performance analysis, tilt report) per player
// in localStorage, so a reload or player switch restores the last report
// instead of costing another Claude call. Entries are { result, at } under
// vac:analysis:<playerKey> / vac:tilt:<playerKey>; "Re-analyze" / "Run tilt
// check" stay the refresh path.
//
// Coach chat messages are deliberately NEVER persisted here (or anywhere):
// the conversation is personal, session-scoped context that lives only in
// component state and travels only with the user's own requests — see
// coachChat() in api.js and the "never collected" list in privacy.html.
//
// Scope: reports only, capped to the MAX_REPORT_PLAYERS most recently
// written players (LRU across both kinds), all storage IO wrapped in
// try/catch, and every read re-validated — localStorage is user-editable.

const PREFIXES = {
  analysis: "vac:analysis:",
  tilt: "vac:tilt:",
};

export const MAX_REPORT_PLAYERS = 6;

function entryAt(raw) {
  try {
    const entry = JSON.parse(raw);
    return entry && typeof entry.at === "number" ? entry.at : 0;
  } catch {
    return 0; // unparseable — treat as oldest so it gets evicted first
  }
}

/** Shape validation for a persisted entry — exported for tests. */
export function isValidReportEntry(kind, entry) {
  if (!entry || typeof entry !== "object") return false;
  if (typeof entry.at !== "number" || !Number.isFinite(entry.at)) return false;
  const r = entry.result;
  if (!r || typeof r !== "object") return false;
  // Kind-specific sanity: the analysis entry is the full /claude/analyze
  // response; the tilt entry is the TiltReport itself.
  if (kind === "analysis") return "analysis" in r;
  if (kind === "tilt") {
    return typeof r.tilt_score === "number" && typeof r.tilt_level === "string";
  }
  return false;
}

/**
 * Read the saved report for a player. Returns { result, at } or null —
 * corrupt JSON, wrong shapes and blocked storage all read as "nothing saved".
 */
export function loadReport(kind, playerKey) {
  const prefix = PREFIXES[kind];
  if (!prefix || !playerKey || playerKey === "none") return null;
  try {
    const raw = localStorage.getItem(prefix + playerKey);
    if (!raw) return null;
    const entry = JSON.parse(raw);
    return isValidReportEntry(kind, entry) ? entry : null;
  } catch {
    return null;
  }
}

/**
 * Save a fresh report as { result, at: Date.now() }, then evict the
 * least-recently-written players beyond the cap. Best-effort: a full or
 * blocked storage is non-fatal.
 */
export function saveReport(kind, playerKey, result) {
  const prefix = PREFIXES[kind];
  if (!prefix || !playerKey || playerKey === "none" || !result) return;
  try {
    localStorage.setItem(
      prefix + playerKey,
      JSON.stringify({ result, at: Date.now() }),
    );
    pruneReportPlayers();
  } catch {
    /* storage full/blocked — non-fatal, the report still renders from state */
  }
}

// LRU across both report kinds: a player's recency is their newest write of
// either kind; evicting a player removes both of their keys.
function pruneReportPlayers() {
  const prefixes = Object.values(PREFIXES);
  const newestAt = new Map(); // playerKey -> newest at
  const storageKeys = new Map(); // playerKey -> [storage keys]
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    const prefix = prefixes.find((p) => key && key.startsWith(p));
    if (!prefix) continue;
    const pk = key.slice(prefix.length);
    const at = entryAt(localStorage.getItem(key));
    if (!newestAt.has(pk) || at > newestAt.get(pk)) newestAt.set(pk, at);
    if (!storageKeys.has(pk)) storageKeys.set(pk, []);
    storageKeys.get(pk).push(key);
  }
  if (newestAt.size <= MAX_REPORT_PLAYERS) return;
  const evict = [...newestAt.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(MAX_REPORT_PLAYERS)
    .flatMap(([pk]) => storageKeys.get(pk));
  for (const key of evict) localStorage.removeItem(key);
}
