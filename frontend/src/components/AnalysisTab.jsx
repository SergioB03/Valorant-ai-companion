import { useState } from "react";
import { analyzeMatches } from "../api.js";
import { stripMarkdown } from "../utils.js";
import { Spinner, ErrorBanner, EmptyState } from "./common.jsx";

const ANALYZE_SIZE = 10;

export default function AnalysisTab({ player }) {
  const [state, setState] = useState({
    loading: false,
    error: null,
    result: null,
  });

  async function run() {
    if (!player || state.loading) return;
    setState({ loading: true, error: null, result: null });
    try {
      const result = await analyzeMatches(
        player.name,
        player.tag,
        player.region,
        ANALYZE_SIZE
      );
      setState({ loading: false, error: null, result });
    } catch (err) {
      setState({ loading: false, error: err.message, result: null });
    }
  }

  if (!player) {
    return (
      <EmptyState
        title="No player selected"
        body="Search a Riot ID above, then let Claude break down the recent matches."
      />
    );
  }

  return (
    <div className="stack">
      <section className="panel">
        <h3 className="panel-title">Performance analysis</h3>
        <p className="panel-sub">
          Claude reviews {player.name}
          <span className="tag">#{player.tag}</span>&apos;s recent matches and
          gives concrete, coach-style feedback.
        </p>
        <button
          type="button"
          className="btn accent"
          onClick={run}
          disabled={state.loading}
        >
          {state.loading
            ? "Analyzing…"
            : state.result
              ? `Re-analyze my last ${state.result.match_count} match${
                  state.result.match_count === 1 ? "" : "es"
                }`
              : "Analyze my last matches"}
        </button>
        {state.loading ? (
          <Spinner label="Claude is reviewing the matches — this can take up to a minute." />
        ) : null}
        {state.error ? (
          <ErrorBanner message={state.error} onRetry={run} />
        ) : null}
      </section>

      {state.result ? (
        <section className="panel">
          <div className="panel-head-row">
            <h3 className="panel-title">Coach report</h3>
            <span className="chip">
              Analyzed your last {state.result.match_count} match
              {state.result.match_count === 1 ? "" : "es"}
            </span>
          </div>
          <div className="prose">{stripMarkdown(state.result.analysis)}</div>
        </section>
      ) : null}
    </div>
  );
}
