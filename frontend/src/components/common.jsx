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

export function Skeleton({ height = 16, width = "100%", style }) {
  return (
    <span
      className="skeleton"
      style={{ height, width, ...style }}
      aria-hidden="true"
    />
  );
}
