import { useState } from "react";
import { askMeta } from "../api.js";
import { stripMarkdown } from "../utils.js";
import { Spinner, ErrorBanner } from "./common.jsx";

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
    try {
      const result = await askMeta(text);
      setState((s) => ({ ...s, loading: false, result }));
    } catch (err) {
      if (err.status === 503) {
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
        <section className="panel">
          <div className="panel-head-row">
            <h3 className="panel-title">Answer</h3>
            <span className="chip">{state.asked}</span>
          </div>
          <div className="prose">{stripMarkdown(state.result.answer)}</div>
          {state.result.sources && state.result.sources.length > 0 ? (
            <details className="sources">
              <summary>Sources ({state.result.sources.length})</summary>
              <ul>
                {state.result.sources.map((s, i) => (
                  <li key={i}>
                    <span className="source-name">
                      {s.source}
                      {s.section ? ` › ${s.section}` : ""}
                    </span>
                    {s.snippet ? (
                      <p className="source-snippet">{s.snippet}…</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
