import { useEffect, useRef, useState } from "react";
import { analyzeMatches, isCancelled } from "../api.js";
import {
  playerKey,
  relativeDate,
  splitParagraphs,
  stripMarkdown,
} from "../utils.js";
import { loadReport, saveReport } from "../reports.js";
import { Spinner, ErrorBanner, EmptyState } from "./common.jsx";
import { Insignia } from "./Insignia.jsx";
import Stopwatch from "./Stopwatch.jsx";
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

function GeneratedChip({ ms }) {
  if (ms == null) return null;
  return <span className="chip">generated in {(ms / 1000).toFixed(1)}s</span>;
}

// Mandatory freshness stamp — a report hydrated from localStorage must never
// pass itself off as freshly generated.
function GeneratedAtChip({ at }) {
  if (at == null) return null;
  return <span className="chip">generated {relativeDate(at)}</span>;
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

function Report({ analysis, matchCount, elapsedMs, at }) {
  // Backward-compatible: older backend returned a plain-text analysis.
  if (!analysis || typeof analysis !== "object") {
    return (
      <section className="panel rise">
        <div className="panel-head-row">
          <h3 className="panel-title">Coach report</h3>
          <div className="chips">
            <MatchCountChip n={matchCount} />
            <GeneratedChip ms={elapsedMs} />
            <GeneratedAtChip at={at} />
          </div>
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
          <div className="chips">
            <MatchCountChip n={matchCount} />
            <GeneratedChip ms={elapsedMs} />
            <GeneratedAtChip at={at} />
          </div>
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
  const [state, setState] = useState(() => {
    // Hydrate the last saved analysis for this player — the keyed remount in
    // App.jsx re-runs this initializer on every player switch. Hydration
    // fires no analyze_run analytics (tracking lives inside run()).
    const saved = player ? loadReport("analysis", playerKey(player)) : null;
    return {
      loading: false,
      error: null,
      result: saved ? saved.result : null,
      cancelled: false,
      elapsedMs: null,
      at: saved ? saved.at : null,
    };
  });
  const abortRef = useRef(null);

  // Abort any in-flight analysis on unmount — player switches remount this
  // tab (keyed wrapper in App), so switching players also cancels cleanly.
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  async function run() {
    if (!player || state.loading) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setState({
      loading: true,
      error: null,
      result: null,
      cancelled: false,
      elapsedMs: null,
      at: null,
    });
    const t0 = performance.now();
    try {
      const result = await analyzeMatches(
        player.name,
        player.tag,
        player.region,
        ANALYZE_SIZE,
        { signal: controller.signal }
      );
      const elapsedMs = Math.round(performance.now() - t0);
      track("analyze_run", {
        match_count: result.match_count ?? 0,
        latency_ms: elapsedMs,
        ok: true,
      });
      saveReport("analysis", playerKey(player), result);
      setState({
        loading: false,
        error: null,
        result,
        cancelled: false,
        elapsedMs,
        at: Date.now(),
      });
    } catch (err) {
      // User-initiated cancel (button, unmount) — a gentle state, not an
      // error, and not an analytics failure event.
      if (isCancelled(err)) {
        setState({
          loading: false,
          error: null,
          result: null,
          cancelled: true,
          elapsedMs: null,
          at: null,
        });
        return;
      }
      track("analyze_run", {
        match_count: 0,
        latency_ms: Math.round(performance.now() - t0),
        ok: false,
      });
      setState({
        loading: false,
        error: err.message,
        result: null,
        cancelled: false,
        elapsedMs: null,
        at: null,
      });
    }
  }

  // Honest caveat: aborting recovers the UI immediately but does not halt the
  // backend's in-flight Claude generation — that spend is already committed.
  function cancel() {
    abortRef.current?.abort();
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
          <div className="wait-row">
            <Spinner label="Claude is reviewing the matches — this can take up to a minute." />
            <Stopwatch running={state.loading} />
            <button
              type="button"
              className="btn ghost small"
              onClick={cancel}
            >
              Cancel
            </button>
          </div>
        ) : null}
        {state.cancelled ? (
          <p className="muted cancelled-note">
            Analysis cancelled — run it again whenever you&apos;re ready.
          </p>
        ) : null}
        {state.error ? (
          <ErrorBanner message={state.error} onRetry={run} />
        ) : null}
      </section>

      {state.result ? (
        <Report
          analysis={state.result.analysis}
          matchCount={state.result.match_count}
          elapsedMs={state.elapsedMs}
          at={state.at}
        />
      ) : null}
    </div>
  );
}
