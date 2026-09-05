import { Component } from "react";
import { track } from "../analytics.js";

/**
 * Class error boundary (hooks can't catch render errors). Used twice:
 * app-level in main.jsx so a render error can never white-screen the site,
 * and per-tab in App.jsx so a crash in one panel leaves the shell and the
 * other tabs usable.
 *
 * The fallback reuses the ErrorBanner styling from common.jsx — same design
 * language, zero new CSS. "Try again" clears the boundary (a transient bad
 * render, e.g. one odd API payload, recovers in place); "Reload" is the
 * escape hatch when it doesn't.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
    this.reset = this.reset.bind(this);
    this.reload = this.reload.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch() {
    // Only the boundary's label goes to analytics — never the error message,
    // which could contain data derived from a Riot ID.
    track("render_error", { where: this.props.label || "app" });
  }

  reset() {
    this.setState({ error: null });
  }

  reload() {
    window.location.reload();
  }

  render() {
    if (!this.state.error) return this.props.children;
    const label = this.props.label || "This part of the app";
    return (
      <div className="error-banner" role="alert">
        <span className="error-icon" aria-hidden="true">
          !
        </span>
        <span className="error-message">
          {label} hit a rendering error. Your data is fine — try again, or
          reload the page.
        </span>
        <button type="button" className="btn ghost small" onClick={this.reset}>
          Try again
        </button>
        <button type="button" className="btn ghost small" onClick={this.reload}>
          Reload
        </button>
      </div>
    );
  }
}
