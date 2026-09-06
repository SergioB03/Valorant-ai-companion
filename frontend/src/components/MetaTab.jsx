import { useEffect, useRef, useState } from "react";
import { askMeta, isCancelled, isDemoMode } from "../api.js";
import { splitParagraphs, stripMarkdown } from "../utils.js";
import { Spinner, AIErrorNotice, AIQuotaCaption } from "./common.jsx";
import { Insignia } from "./Insignia.jsx";
import Stopwatch from "./Stopwatch.jsx";
import { track } from "../analytics.js";

const EXAMPLES = [
  "What changed in the most recent patches?",
  "Which agents are strong in ranked right now?",
  "How does the economy work — when should I save?",
  "How do I stop tilting after two losses?",
];

/**
 * Source citations. Chips are tap-to-reveal (the snippet used to live only in
 * a hover title attribute — invisible on touch); when the backend marks which
 * sources the answer actually drew on (`used: true`, optional field), used
 * chips get a badge and unused ones are de-emphasized.
 */
function SourceList({ sources }) {
  const [expanded, setExpanded] = useState(null);
  const anyUsed = sources.some((s) => s && s.used === true);
  const open = expanded != null ? sources[expanded] : null;

  return (
    <div className="sources-row">
      <span className="mini-title">Sources ({sources.length})</span>
      <div className="chips">
        {sources.map((s, i) => {
          const dimmed = anyUsed && s.used !== true;
          return (
            <button
              key={i}
              type="button"
              className={`chip chip-btn source-chip${
                dimmed ? " source-unused" : ""
              }${expanded === i ? " open" : ""}`}
              aria-expanded={expanded === i}
              onClick={() => setExpanded(expanded === i ? null : i)}
            >
              {s.source}
              {s.section ? ` › ${s.section}` : ""}
              {s.used === true ? (
                <span className="source-used-badge">used</span>
              ) : null}
            </button>
          );
        })}
      </div>
      {open && open.snippet ? (
        <blockquote className="source-snippet">
          {open.snippet}…
        </blockquote>
      ) : null}
    </div>
  );
}

export default function MetaTab() {
  const [question, setQuestion] = useState("");
  const [state, setState] = useState({
    loading: false,
    error: null,
    unavailable: false,
    cancelled: false,
    asked: "",
    result: null,
    elapsedMs: null,
  });
  const abortRef = useRef(null);

  // Abort an in-flight question on unmount.
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  async function ask(q) {
    const text = (q || "").trim();
    if (!text || state.loading) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setQuestion(text);
    setState({
      loading: true,
      error: null,
      unavailable: false,
      cancelled: false,
      asked: text,
      result: null,
      elapsedMs: null,
    });
    const t0 = performance.now();
    try {
      const result = await askMeta(text, { signal: controller.signal });
      const elapsedMs = Math.round(performance.now() - t0);
      // Demo answers are canned fixtures — demo_started is the demo's only
      // analytics event.
      if (!isDemoMode()) {
        track("meta_question", {
          latency_ms: elapsedMs,
          ok: true,
          unavailable: false,
        });
      }
      setState((s) => ({ ...s, loading: false, result, elapsedMs }));
    } catch (err) {
      if (isCancelled(err)) {
        setState((s) => ({ ...s, loading: false, cancelled: true }));
        return;
      }
      const unavailable = err.status === 503;
      if (!isDemoMode()) {
        track("meta_question", {
          latency_ms: Math.round(performance.now() - t0),
          ok: false,
          unavailable,
        });
      }
      if (unavailable) {
        setState((s) => ({ ...s, loading: false, unavailable: true }));
      } else {
        // Whole error object — AIErrorNotice renders the friendly
        // daily-quota / per-minute copy from its header-derived fields.
        setState((s) => ({ ...s, loading: false, error: err }));
      }
    }
  }

  // Recovers the UI; an in-flight backend generation still completes.
  function cancel() {
    abortRef.current?.abort();
  }

  function handleSubmit(e) {
    e.preventDefault();
    ask(question);
  }

  return (
    <div className="stack">
      <section className="panel">
        <h3 className="panel-title">Meta Q&amp;A</h3>
        <p className="panel-sub">
          Ask about patches, agents, maps, economy, ranked or improvement.
          Answers come from a curated Valorant knowledge base (RAG), so they
          cite their sources.
        </p>
        <form className="meta-form" onSubmit={handleSubmit}>
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. What did the last patch change?"
            aria-label="Your question"
            disabled={state.loading}
          />
          <button
            type="submit"
            className="btn accent"
            disabled={state.loading || !question.trim()}
          >
            Ask
          </button>
        </form>
        <div className="chips example-chips">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              className="chip chip-btn"
              onClick={() => ask(ex)}
              disabled={state.loading}
            >
              {ex}
            </button>
          ))}
        </div>
        <AIQuotaCaption />
        <p className="patch-link-line muted">
          Prefer to read? <a href="/patch/">Browse the patch digests</a> —
          summarized patch notes, no AI action needed.
        </p>
      </section>

      {state.loading ? (
        <section className="panel">
          <div className="wait-row">
            <Spinner label="Searching the knowledge base and asking Claude…" />
            <Stopwatch running={state.loading} />
            <button type="button" className="btn ghost small" onClick={cancel}>
              Cancel
            </button>
          </div>
        </section>
      ) : null}

      {state.cancelled ? (
        <section className="panel">
          <p className="muted cancelled-note">
            Question cancelled — ask again whenever you&apos;re ready.
          </p>
        </section>
      ) : null}

      {state.unavailable ? (
        <section className="panel">
          <div className="notice">
            <h4 className="mini-title">Knowledge base offline</h4>
            <p className="muted">
              The meta Q&amp;A service isn&apos;t available right now (the RAG
              index / ChromaDB isn&apos;t running on the backend). Everything
              else still works — try again later.
            </p>
          </div>
        </section>
      ) : null}

      {state.error ? (
        <AIErrorNotice error={state.error} onRetry={() => ask(state.asked)} />
      ) : null}

      {state.result ? (
        <section className="panel rise">
          <div className="panel-head-row">
            <h3 className="panel-title">Intel</h3>
            <div className="chips">
              {state.elapsedMs != null ? (
                <span className="chip">
                  generated in {(state.elapsedMs / 1000).toFixed(1)}s
                </span>
              ) : null}
              <Insignia kind="neutral" label="Knowledge base" />
            </div>
          </div>
          <span className="chip asked-chip">{state.asked}</span>
          <div className="answer-body">
            {splitParagraphs(stripMarkdown(state.result.answer)).map(
              (p, i) => (
                <p
                  key={i}
                  className="rise"
                  style={{ animationDelay: `${80 + i * 70}ms` }}
                >
                  {p}
                </p>
              )
            )}
          </div>
          {state.result.corpus_vintage ? (
            <p className="vintage-caption">
              Knowledge base: {state.result.corpus_vintage}
            </p>
          ) : null}
          {state.result.sources && state.result.sources.length > 0 ? (
            <SourceList
              key={state.asked}
              sources={state.result.sources}
            />
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
