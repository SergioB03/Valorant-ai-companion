import { useState } from "react";
import { askMeta } from "../api.js";
import { splitParagraphs, stripMarkdown } from "../utils.js";
import { Spinner, ErrorBanner } from "./common.jsx";
import { Insignia } from "./Insignia.jsx";
import { track } from "../analytics.js";

const EXAMPLES = [
  "What changed in the most recent patches?",
  "Which agents are strong in ranked right now?",
  "How does the economy work — when should I save?",
  "How do I stop tilting after two losses?",
];

export default function MetaTab() {
  const [question, setQuestion] = useState("");
  const [state, setState] = useState({
    loading: false,
    error: null,
    unavailable: false,
    asked: "",
    result: null,
  });

  async function ask(q) {
    const text = (q || "").trim();
    if (!text || state.loading) return;
    setQuestion(text);
    setState({
      loading: true,
      error: null,
      unavailable: false,
      asked: text,
      result: null,
    });
    const t0 = performance.now();
    try {
      const result = await askMeta(text);
      track("meta_question", {
        latency_ms: Math.round(performance.now() - t0),
        ok: true,
        unavailable: false,
      });
      setState((s) => ({ ...s, loading: false, result }));
    } catch (err) {
      const unavailable = err.status === 503;
      track("meta_question", {
        latency_ms: Math.round(performance.now() - t0),
        ok: false,
        unavailable,
      });
      if (unavailable) {
        setState((s) => ({ ...s, loading: false, unavailable: true }));
      } else {
        setState((s) => ({ ...s, loading: false, error: err.message }));
      }
    }
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
      </section>

      {state.loading ? (
        <section className="panel">
          <Spinner label="Searching the knowledge base and asking Claude…" />
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
        <ErrorBanner message={state.error} onRetry={() => ask(state.asked)} />
      ) : null}

      {state.result ? (
        <section className="panel rise">
          <div className="panel-head-row">
            <h3 className="panel-title">Intel</h3>
            <Insignia kind="neutral" label="Knowledge base" />
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
          {state.result.sources && state.result.sources.length > 0 ? (
            <div className="sources-row">
              <span className="mini-title">
                Sources ({state.result.sources.length})
              </span>
              <div className="chips">
                {state.result.sources.map((s, i) => (
                  <span
                    key={i}
                    className="chip source-chip"
                    title={s.snippet ? `${s.snippet}…` : undefined}
                  >
                    {s.source}
                    {s.section ? ` › ${s.section}` : ""}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
