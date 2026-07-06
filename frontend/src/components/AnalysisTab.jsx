import { useState } from "react";
import { analyzeMatches } from "../api.js";
import { stripMarkdown, splitParagraphs } from "../utils.js";
import { Spinner, ErrorBanner, EmptyState } from "./common.jsx";
import { Insignia } from "./Insignia.jsx";
import { track } from "../analytics.js";

const ANALYZE_SIZE = 10;

function MatchCountChip({ n }) {
  if (n == null) return null;
  return (
    <span className="chip">
      Analyzed your last {n} competitive match{n === 1 ? "" : "es"}
    </span>
  );
}

function InsigniaList({ kind, label, items, baseDelay = 0, emptyText }) {
  if (!items || items.length === 0) {
    return <p className="muted">{emptyText}</p>;
  }
  return (
    <ul className="insignia-list">
      {items.map((text, i) => (
        <li
          key={i}
          className={`insignia-item kind-${kind} rise${
            kind === "weakness" ? " pulse" : ""
          }`}
          style={{ animationDelay: `${baseDelay + i * 90}ms` }}
        >
          <Insignia kind={kind} label={label} />
          <p>{stripMarkdown(String(text))}</p>
        </li>
      ))}
    </ul>
  );
}

function Report({ analysis, matchCount }) {
  // Backward-compatible: older backend returned a plain-text analysis.
  if (!analysis || typeof analysis !== "object") {
    return (
      <section className="panel rise">
        <div className="panel-head-row">
          <h3 className="panel-title">Coach report</h3>
          <MatchCountChip n={matchCount} />
        </div>
        <div className="prose">{stripMarkdown(String(analysis ?? ""))}</div>
      </section>
    );
  }

  const strengths = Array.isArray(analysis.strengths) ? analysis.strengths : [];
  const weaknesses = Array.isArray(analysis.weaknesses)
    ? analysis.weaknesses
    : [];
  const overviewParas = splitParagraphs(stripMarkdown(analysis.overview || ""));

  return (
    <>
      <section className="panel rise">
        <div className="panel-head-row">
          <h3 className="panel-title">The read</h3>
          <MatchCountChip n={matchCount} />
        </div>
        {overviewParas.length > 0 ? (
          <div className="overview-body">
            {overviewParas.map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>
        ) : (
          <p className="muted">No overview came back for this batch.</p>
        )}
      </section>

      {analysis.tilt_warning ? (
        <section
          className="panel warning-banner rise pulse"
          style={{ animationDelay: "90ms" }}
          role="alert"
        >
          <Insignia kind="weakness" label="Tilt warning" />
          <p className="warning-text">
            {stripMarkdown(String(analysis.tilt_warning))}
          </p>
        </section>
      ) : null}

      <div className="report-grid">
        <section className="panel rise" style={{ animationDelay: "160ms" }}>
          <h3 className="panel-title">Locked in</h3>
          <InsigniaList
            kind="strength"
            label="Strength"
            items={strengths}
            baseDelay={260}
            emptyText="Nothing stood out as a strength this batch — rough patch, it happens."
          />
        </section>
        <section className="panel rise" style={{ animationDelay: "230ms" }}>
          <h3 className="panel-title">Leaks to patch</h3>
          <InsigniaList
            kind="weakness"
            label="Weakness"
            items={weaknesses}
            baseDelay={330}
            emptyText="No recurring leaks found. Clean sheet."
          />
        </section>
      </div>

      {analysis.tip ? (
        <section
          className="panel tip-card rise"
          style={{ animationDelay: "380ms" }}
        >
          <div className="panel-head-row">
            <h3 className="panel-title">Next game</h3>
            <Insignia kind="tip" label="Tactical tip" />
          </div>
          <p className="tip-text">{stripMarkdown(String(analysis.tip))}</p>
        </section>
      ) : null}
    </>
  );
}

export default function AnalysisTab({ player }) {
  const [state, setState] = useState({
    loading: false,
    error: null,
    result: null,
  });

  async function run() {
    if (!player || state.loading) return;
    setState({ loading: true, error: null, result: null });
    const t0 = performance.now();
    try {
      const result = await analyzeMatches(
        player.name,
        player.tag,
        player.region,
        ANALYZE_SIZE
      );
      track("analyze_run", {
        match_count: result.match_count ?? 0,
        latency_ms: Math.round(performance.now() - t0),
        ok: true,
      });
      setState({ loading: false, error: null, result });
    } catch (err) {
      track("analyze_run", {
        match_count: 0,
        latency_ms: Math.round(performance.now() - t0),
        ok: false,
      });
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
              : "Analyze my last competitive matches"}
        </button>
        {state.loading ? (
          <Spinner label="Claude is reviewing the matches — this can take up to a minute." />
        ) : null}
        {state.error ? (
          <ErrorBanner message={state.error} onRetry={run} />
        ) : null}
      </section>

      {state.result ? (
        <Report
          analysis={state.result.analysis}
          matchCount={state.result.match_count}
        />
      ) : null}
    </div>
  );
}
