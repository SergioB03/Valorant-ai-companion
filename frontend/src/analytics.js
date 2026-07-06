// Self-contained, anonymous analytics client. No deps, no PII — events carry
// random IDs plus tiny prop payloads (never riot names/tags). Fully disabled
// when the browser sends Do Not Track or the build sets VITE_ANALYTICS=off.

const API = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(
  /\/+$/,
  ""
);
const ENDPOINT = `${API}/analytics/events`;

const VID_KEY = "vac:vid"; // localStorage — stable anonymous visitor id
const SID_KEY = "vac:sid"; // sessionStorage — per browser session
const SESSION_FLAG = "vac:session-started";

const MAX_QUEUE = 50; // hard cap; oldest events drop beyond this
const MAX_BATCH = 25; // server accepts at most 25 events per request
const FLUSH_AT = 10; // flush early once this many events are queued
const FLUSH_EVERY_MS = 10000;

const DISABLED =
  import.meta.env.VITE_ANALYTICS === "off" ||
  (typeof navigator !== "undefined" && navigator.doNotTrack === "1");

function safeGet(storage, key) {
  try {
    return storage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(storage, key, value) {
  try {
    storage.setItem(key, value);
  } catch {
    /* storage blocked/full — ids fall back to per-load values */
  }
}

function uuid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;
}

function getId(storage, key) {
  let id = safeGet(storage, key);
  if (!id) {
    id = uuid();
    safeSet(storage, key, id);
  }
  return id;
}

// Queue items are { event, retried } — a failed batch is re-queued exactly
// once, then dropped, so a dead backend never grows memory unbounded.
let queue = [];
let flushing = false;

function push(event, retried = false) {
  queue.push({ event, retried });
  while (queue.length > MAX_QUEUE) queue.shift();
}

function requeue(batch) {
  const retryable = batch
    .filter((item) => !item.retried)
    .map((item) => ({ event: item.event, retried: true }));
  // Keep newest MAX_QUEUE entries — oldest (the retried ones) drop first.
  queue = [...retryable, ...queue].slice(-MAX_QUEUE);
}

function payload(batch) {
  return JSON.stringify({
    visitor_id: getId(localStorage, VID_KEY),
    session_id: getId(sessionStorage, SID_KEY),
    events: batch.map((item) => item.event),
  });
}

async function flush() {
  if (DISABLED || flushing || queue.length === 0) return;
  flushing = true;
  const batch = queue.splice(0, MAX_BATCH);
  try {
    const res = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload(batch),
      keepalive: true,
    });
    if (!res.ok) requeue(batch);
  } catch {
    requeue(batch);
  } finally {
    flushing = false;
  }
}

// Tab going hidden may be the last chance to deliver — sendBeacon survives
// page teardown where fetch may not.
function beaconFlush() {
  if (DISABLED || queue.length === 0) return;
  if (typeof navigator === "undefined" || !navigator.sendBeacon) {
    flush();
    return;
  }
  while (queue.length > 0) {
    const batch = queue.splice(0, MAX_BATCH);
    const blob = new Blob([payload(batch)], { type: "application/json" });
    if (!navigator.sendBeacon(ENDPOINT, blob)) {
      requeue(batch);
      break;
    }
  }
}

export function track(name, props = {}) {
  if (DISABLED) return;
  push({
    name,
    ts: Date.now(),
    path: typeof location !== "undefined" ? location.pathname : "",
    props,
  });
  if (queue.length >= FLUSH_AT) flush();
}

// Fired once per browser session; sends only the referrer's host, never the
// full URL.
export function trackSessionStart() {
  if (DISABLED) return;
  if (safeGet(sessionStorage, SESSION_FLAG)) return;
  safeSet(sessionStorage, SESSION_FLAG, "1");
  let referrerHost = "";
  try {
    if (document.referrer) referrerHost = new URL(document.referrer).host;
  } catch {
    /* malformed referrer — send empty host */
  }
  track("session_start", { referrer_host: referrerHost });
}

if (!DISABLED && typeof window !== "undefined") {
  setInterval(flush, FLUSH_EVERY_MS);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") beaconFlush();
  });
}
