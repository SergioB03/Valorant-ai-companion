import { useEffect, useRef, useState } from "react";
import { getQuotaLimit, isDemoMode } from "../api.js";
import { buildShareUrl } from "../utils.js";
import { track } from "../analytics.js";

export function Spinner({ label }) {
  return (
    <div className="spinner-wrap" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span className="spinner-label">{label || "Loading…"}</span>
    </div>
  );
}

export function ErrorBanner({ message, onRetry }) {
  return (
    <div className="error-banner" role="alert">
      <span className="error-icon" aria-hidden="true">
        !
      </span>
      <span className="error-message">{message}</span>
      {onRetry ? (
        <button type="button" className="btn ghost small" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({ title, body }) {
  return (
    <div className="empty-state">
      <svg
        className="empty-icon"
        viewBox="0 0 48 48"
        aria-hidden="true"
        focusable="false"
      >
        <circle
          cx="24"
          cy="24"
          r="14"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        />
        <line x1="24" y1="2" x2="24" y2="14" stroke="currentColor" strokeWidth="2" />
        <line x1="24" y1="34" x2="24" y2="46" stroke="currentColor" strokeWidth="2" />
        <line x1="2" y1="24" x2="14" y2="24" stroke="currentColor" strokeWidth="2" />
        <line x1="34" y1="24" x2="46" y2="24" stroke="currentColor" strokeWidth="2" />
        <circle cx="24" cy="24" r="2.5" fill="currentColor" />
      </svg>
      <h3>{title}</h3>
      {body ? <p>{body}</p> : null}
    </div>
  );
}

/**
 * Error rendering for the AI-spending actions. Three different 429s exist
 * (daily quota, per-minute slowapi, Henrik upstream), so the friendly
 * "resets at midnight" copy is keyed ONLY on the X-Quota-Exhausted header
 * that api.js lifts into err.quotaExhausted — never on the status alone.
 * The daily-quota state deliberately has no Retry button: retrying cannot
 * succeed until the UTC-midnight reset.
 */
export function AIErrorNotice({ error, onRetry }) {
  if (!error) return null;
  if (error.quotaExhausted) {
    const hours =
      Number.isFinite(error.retryAfterSeconds) && error.retryAfterSeconds > 0
        ? Math.max(1, Math.round(error.retryAfterSeconds / 3600))
        : null;
    return (
      <div className="quota-notice" role="status">
        <span className="quota-icon" aria-hidden="true">
          !
        </span>
        <span>
          Out of free AI actions today — resets at midnight UTC
          {hours != null ? ` (about ${hours}h from now)` : ""}. The dashboard
          and your saved reports still work.
        </span>
      </div>
    );
  }
  const message =
    error.status === 429
      ? "Slow down a moment — that's the per-minute limit, not your daily quota. Try again in a few seconds."
      : error.message;
  return <ErrorBanner message={message} onRetry={onRetry} />;
}

/**
 * Static honest-cost caption for the three AI buttons. The limit comes from
 * the X-Quota-Limit header (last seen value) — never hardcoded, since the
 * backend's quota is env-configurable. Hidden in demo mode: sample data
 * spends nothing.
 */
export function AIQuotaCaption() {
  if (isDemoMode()) return null;
  const limit = getQuotaLimit();
  return (
    <p className="ai-caption">
      Uses 1 of your {limit != null ? `${limit} ` : ""}free daily AI actions.
    </p>
  );
}

/**
 * The trivial "Copy link" affordance for the shareable deep links. Copies
 * the canonical share URL for the given player+tab; the analytics event
 * carries the tab only — never an identity.
 */
export function CopyLinkButton({ player, tab }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef(null);

  useEffect(() => () => clearTimeout(timerRef.current), []);

  async function copy() {
    const url = `${window.location.origin}${buildShareUrl(player, tab)}`;
    try {
      await navigator.clipboard.writeText(url);
      track("copy_link", { tab });
      setCopied(true);
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard blocked — the address bar still carries the same URL */
    }
  }

  if (typeof navigator === "undefined" || !navigator.clipboard) return null;
  return (
    <button type="button" className="chip chip-btn" onClick={copy}>
      {copied ? "Link copied ✓" : "Copy link"}
    </button>
  );
}

export function Skeleton({ height = 16, width = "100%", style }) {
  return (
    <span
      className="skeleton"
      style={{ height, width, ...style }}
      aria-hidden="true"
    />
  );
}
