import { useCallback, useEffect, useRef, useState } from "react";
import { tiltCheck, coachChat, getMentalProfile, isCancelled } from "../api.js";
import {
  LEVEL_COLORS,
  playerKey,
  relativeDate,
  shortDateTime,
  splitParagraphs,
  stripMarkdown,
} from "../utils.js";
import { loadReport, saveReport } from "../reports.js";
import { Spinner, ErrorBanner, EmptyState } from "./common.jsx";
import { Insignia, AgentBadge } from "./Insignia.jsx";
import TiltMeter from "./TiltMeter.jsx";
import Sparkline from "./Sparkline.jsx";
import Stopwatch from "./Stopwatch.jsx";
import { track } from "../analytics.js";

// Starter prompts for an empty chat — same chip pattern as MetaTab's
// EXAMPLES. Each routes through the exact same send() path as a typed
// message, so the optimistic-rollback error handling and the
// coach_message_sent analytics behave identically either way.
const STARTERS = [
  "Why do I keep losing on Icebox?",
  "Should I keep queueing tonight?",
  "Help me reset after that game",
];

function TrendBadge({ trend }) {
  const map = {
    improving: { label: "Improving", color: "#4ade80" },
    worsening: { label: "Worsening", color: "#ff4655" },
    stable: { label: "Stable", color: "#9aa7b3" },
    insufficient_data: { label: "Not enough data yet", color: "#9aa7b3" },
  };
  const t = map[trend] || map.insufficient_data;
  return (
    <span className="chip" style={{ color: t.color, borderColor: t.color }}>
      {t.label}
    </span>
  );
}

// Map signal severity onto the shared sentiment insignia contract:
// critical/high burn red (Omen, pulsing), medium reads as a heads-up
// (Brimstone amber), low is a neutral pattern note (Cypher).
function severityKind(severity) {
  if (severity === "critical" || severity === "high") return "weakness";
  if (severity === "medium") return "tip";
  return "neutral";
}

function SignalList({ signals }) {
  if (!signals || signals.length === 0) {
    return (
      <div className="insignia-item kind-strength rise clean-bill">
        <Insignia kind="strength" label="Clean bill" />
        <p>No tilt signals detected. Mental is solid — keep queueing.</p>
      </div>
    );
  }
  return (
    <ul className="insignia-list">
      {signals.map((s, i) => {
        const kind = severityKind(s.severity);
        const hot = kind === "weakness";
        return (
          <li
            key={i}
            className={`insignia-item kind-${kind} rise${hot ? " pulse" : ""}`}
            style={{ animationDelay: `${i * 80}ms` }}
          >
            <Insignia kind={kind} label={s.severity} />
            <div className="signal-body">
              <span className="signal-type">
                {(s.type || "").replace(/_/g, " ")}
              </span>
              <span className="signal-detail">{s.detail}</span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

// Coach message styled as an in-game team-comms card.
function CommsCard({ text }) {
  const paras = splitParagraphs(stripMarkdown(text));
  return (
    <div className="comms-card rise">
      <div className="comms-avatar" aria-hidden="true">
        <AgentBadge kind="mental" size={44} />
      </div>
      <div className="comms-body">
        <div className="comms-head">
          <span className="comms-name">Team comms — Coach</span>
          <Insignia kind="mental" label="Reset protocol" />
        </div>
        <blockquote className="comms-quote">
          {paras.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </blockquote>
      </div>
    </div>
  );
}

function TrendPair({ label, trend, digits }) {
  if (!trend || trend.recent == null || trend.baseline == null) return null;
  const worse = trend.recent < trend.baseline;
  return (
    <div className="trend-pair">
      <span className="stat-label">{label}</span>
      <span>
        <strong style={{ color: worse ? "#fb923c" : "#4ade80" }}>
          {Number(trend.recent).toFixed(digits)}
        </strong>{" "}
        <span className="muted">recent vs baseline</span>{" "}
        {Number(trend.baseline).toFixed(digits)}
      </span>
    </div>
  );
}

export default function MentalCoachTab({ player, active }) {
  const [tilt, setTilt] = useState(() => {
    // Hydrate the last saved tilt report for this player — the keyed remount
    // in App.jsx re-runs this initializer on every player switch. Hydration
    // fires no tilt_check analytics (tracking lives inside runTiltCheck).
    const saved = player ? loadReport("tilt", playerKey(player)) : null;
    return {
      loading: false,
      error: null,
      report: saved ? saved.result : null,
      cancelled: false,
      elapsedMs: null,
      at: saved ? saved.at : null,
    };
  });
  // Chat messages are deliberately NEVER persisted (no localStorage, no
  // backend transcript) — the conversation is personal, session-scoped
  // context that only ever travels with the user's own requests. Only the
  // tilt *report* above is cached; see src/reports.js.
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState(null);
  const [profile, setProfile] = useState({ loading: false, error: null, data: null });
  const chatRef = useRef(null);
  const aliveRef = useRef(true);
  const activatedRef = useRef(false);
  const tiltAbortRef = useRef(null);
  const chatAbortRef = useRef(null);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
      // Abort in-flight requests on unmount (player switches remount this
      // tab via the keyed wrapper in App).
      tiltAbortRef.current?.abort();
      chatAbortRef.current?.abort();
    };
  }, []);

  const loadProfile = useCallback(() => {
    if (!player) return;
    setProfile((p) => ({ ...p, loading: true, error: null }));
    getMentalProfile(player.name, player.tag)
      .then((data) => {
        if (aliveRef.current) setProfile({ loading: false, error: null, data });
      })
      .catch((err) => {
        if (aliveRef.current)
          setProfile({ loading: false, error: err.message, data: null });
      });
  }, [player]);

  // Fetch the profile on first *activation* of this tab, not on mount — the
  // tab is mounted-but-[hidden] on every search, and /mental/profile has its
  // own 15/min rate budget, so loading it for a tab nobody opened was a
  // wasted request per search.
  useEffect(() => {
    if (active && !activatedRef.current) {
      activatedRef.current = true;
      loadProfile();
    }
  }, [active, loadProfile]);

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [messages, sending]);

  async function runTiltCheck() {
    if (!player || tilt.loading) return;
    const controller = new AbortController();
    tiltAbortRef.current = controller;
    setTilt({
      loading: true,
      error: null,
      report: null,
      cancelled: false,
      elapsedMs: null,
      at: null,
    });
    const t0 = performance.now();
    try {
      const report = await tiltCheck(player.name, player.tag, player.region, 10, {
        signal: controller.signal,
      });
      const elapsedMs = Math.round(performance.now() - t0);
      track("tilt_check", {
        tilt_level: report.tilt_level,
        tilt_score: report.tilt_score,
        latency_ms: elapsedMs,
        ok: true,
      });
      saveReport("tilt", playerKey(player), report);
      if (!aliveRef.current) return;
      setTilt({
        loading: false,
        error: null,
        report,
        cancelled: false,
        elapsedMs,
        at: Date.now(),
      });
      loadProfile();
    } catch (err) {
      if (isCancelled(err)) {
        if (aliveRef.current)
          setTilt({
            loading: false,
            error: null,
            report: null,
            cancelled: true,
            elapsedMs: null,
            at: null,
          });
        return;
      }
      track("tilt_check", {
        latency_ms: Math.round(performance.now() - t0),
        ok: false,
      });
      if (!aliveRef.current) return;
      setTilt({
        loading: false,
        error: err.message,
        report: null,
        cancelled: false,
        elapsedMs: null,
        at: null,
      });
    }
  }

  // Client-side cancel: recovers the UI, though an in-flight Claude
  // generation on the backend still runs to completion.
  function cancelTiltCheck() {
    tiltAbortRef.current?.abort();
  }

  // Single send path for typed messages AND starter chips — the optimistic
  // append, rollback-and-restore on failure, and analytics live only here.
  async function send(rawText) {
    const text = (rawText || "").trim();
    if (!text || sending || !player) return;
    setChatError(null);
    setInput("");
    // Snapshot the conversation *before* this message — it becomes the context
    // sent with the request (the server keeps no transcript of its own).
    const priorTurns = messages;
    setMessages((m) => [...m, { role: "user", text }]);
    setSending(true);
    const controller = new AbortController();
    chatAbortRef.current = controller;
    const t0 = performance.now();
    try {
      const res = await coachChat(
        player.name,
        player.tag,
        player.region,
        text,
        priorTurns,
        { signal: controller.signal },
      );
      track("coach_message_sent", {
        latency_ms: Math.round(performance.now() - t0),
        ok: true,
      });
      if (!aliveRef.current) return;
      setMessages((m) => [
        ...m,
        {
          role: "coach",
          text: stripMarkdown(res.reply),
          tiltScore: res.tilt_score,
          tiltLevel: res.tilt_level,
        },
      ]);
      loadProfile();
    } catch (err) {
      // Abort on unmount — not a failure worth an analytics event, and the
      // component is gone anyway.
      if (isCancelled(err)) return;
      track("coach_message_sent", {
        latency_ms: Math.round(performance.now() - t0),
        ok: false,
      });
      if (!aliveRef.current) return;
      // Roll back the optimistic user bubble and restore the draft so the
      // user can retry the send.
      setMessages((m) => m.slice(0, -1));
      setInput(text);
      setChatError(err.message);
    } finally {
      if (aliveRef.current) setSending(false);
    }
  }

  function handleChatSubmit(e) {
    e.preventDefault();
    send(input);
  }

  if (!player) {
    return (
      <EmptyState
        title="No player selected"
        body="Search a Riot ID above to run a tilt check and talk to the mental coach."
      />
    );
  }

  const report = tilt.report;
  const snapshots = (profile.data && profile.data.snapshots) || [];
  const sessions = (profile.data && profile.data.sessions) || [];
  const sparkPoints = [...snapshots]
    .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))
    .map((s) => ({
      value: s.tilt_score ?? 0,
      color: LEVEL_COLORS[s.tilt_level],
      label: `${s.tilt_score} (${s.tilt_level}) — ${shortDateTime(s.created_at)}`,
    }));

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-head-row">
          <h3 className="panel-title">Tilt check</h3>
          <button
            type="button"
            className="btn accent"
            onClick={runTiltCheck}
            disabled={tilt.loading}
          >
            {tilt.loading ? "Checking…" : "Run tilt check"}
          </button>
        </div>
        <p className="panel-sub">
          Scans your last 10 competitive matches for loss streaks, KDA/headshot drops and
          trigger maps or agents, then asks the coach for a read.
        </p>

        {tilt.loading ? (
          <div className="wait-row">
            <Spinner label="Crunching recent matches and asking the coach…" />
            <Stopwatch running={tilt.loading} />
            <button
              type="button"
              className="btn ghost small"
              onClick={cancelTiltCheck}
            >
              Cancel
            </button>
          </div>
        ) : null}
        {tilt.cancelled ? (
          <p className="muted cancelled-note">
            Tilt check cancelled — run it again whenever you&apos;re ready.
          </p>
        ) : null}
        {tilt.error ? (
          <ErrorBanner message={tilt.error} onRetry={runTiltCheck} />
        ) : null}

        {report ? (
          <div className="stack">
            {tilt.elapsedMs != null || tilt.at != null ? (
              <div className="chips">
                {tilt.elapsedMs != null ? (
                  <span className="chip">
                    generated in {(tilt.elapsedMs / 1000).toFixed(1)}s
                  </span>
                ) : null}
                {/* Mandatory freshness stamp — a hydrated report must never
                    pass itself off as freshly generated. */}
                {tilt.at != null ? (
                  <span className="chip">generated {relativeDate(tilt.at)}</span>
                ) : null}
              </div>
            ) : null}
            <TiltMeter score={report.tilt_score} level={report.tilt_level} />

            <div className="tilt-grid">
              <div className="tilt-col">
                <h4 className="mini-title">Signals</h4>
                <SignalList signals={report.signals} />
                <TrendPair label="KDA" trend={report.kda_trend} digits={2} />
                <TrendPair label="Headshot %" trend={report.hs_trend} digits={1} />
              </div>
              <div className="tilt-col">
                <h4 className="mini-title">Triggers</h4>
                {report.triggers &&
                ((report.triggers.maps || []).length > 0 ||
                  (report.triggers.agents || []).length > 0) ? (
                  <div className="chips">
                    {(report.triggers.maps || []).map((m) => (
                      <span key={`m-${m}`} className="chip">
                        Map · {m}
                      </span>
                    ))}
                    {(report.triggers.agents || []).map((a) => (
                      <span key={`a-${a}`} className="chip">
                        Agent · {a}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="muted">No trigger maps or agents found.</p>
                )}
                <h4 className="mini-title">Loss streak</h4>
                <p>
                  {report.current_loss_streak > 0
                    ? `${report.current_loss_streak} loss${
                        report.current_loss_streak === 1 ? "" : "es"
                      } in a row`
                    : "No active loss streak"}
                </p>
              </div>
            </div>

            <div className="callout">
              <span className="stat-label">Recommendation</span>
              <p>{report.recommendation}</p>
            </div>

            {report.coach_message ? (
              <CommsCard text={report.coach_message} />
            ) : null}
          </div>
        ) : null}

        {!report && !tilt.loading && !tilt.error ? (
          <p className="muted">
            Run a tilt check to see the 0–100 tilt meter and a coach read on
            your recent games.
          </p>
        ) : null}
      </section>

      <section className="panel">
        <h3 className="panel-title">Talk to the coach</h3>
        {/* AI disclosure. Shown before the first message and kept visible for
            the whole session rather than tied to messages.length, because both
            Anthropic's usage policy (consumer-facing chatbots must disclose
            they are AI) and EU AI Act Art. 50(1) want the disclosure present
            at the start of every session — and a "coach" that types back is
            exactly the case where a person might assume otherwise. */}
        <p className="ai-disclosure">
          You're talking to an AI, not a person — replies are generated by
          Claude. It isn't a therapist or a substitute for professional help.
        </p>
        <div className="chat-box">
          {/* role="log" (implicit aria-live=polite) — coach replies and the
              typing indicator arrive into an existing view, and this is the
              only way a screen reader hears them. */}
          <div
            className="chat-messages"
            ref={chatRef}
            role="log"
            aria-label="Coach conversation"
          >
            {messages.length === 0 ? (
              <div className="chat-hint chat-starters">
                <p className="muted">Ask anything, or start with one of these:</p>
                <div className="chips">
                  {STARTERS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      className="chip chip-btn"
                      onClick={() => send(s)}
                      disabled={sending}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m, i) => (
                <div key={i} className={`chat-msg ${m.role}`}>
                  <div className="chat-bubble">
                    <div className="prose">{m.text}</div>
                    {m.role === "coach" && m.tiltScore != null ? (
                      <span
                        className="chip chat-chip"
                        style={{
                          color: LEVEL_COLORS[m.tiltLevel] || "#9aa7b3",
                          borderColor: LEVEL_COLORS[m.tiltLevel] || "#9aa7b3",
                        }}
                      >
                        tilt {m.tiltScore} · {m.tiltLevel}
                      </span>
                    ) : null}
                  </div>
                </div>
              ))
            )}
            {sending ? (
              <div className="chat-msg coach">
                <div className="chat-bubble typing">Coach is typing…</div>
              </div>
            ) : null}
          </div>
          {chatError ? <ErrorBanner message={chatError} /> : null}
          <form className="chat-input" onSubmit={handleChatSubmit}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Message the coach…"
              aria-label="Message the coach"
              disabled={sending}
            />
            <button
              type="submit"
              className="btn accent"
              disabled={sending || !input.trim()}
            >
              Send
            </button>
          </form>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head-row">
          <h3 className="panel-title">Mental profile</h3>
          {profile.data ? <TrendBadge trend={profile.data.trend} /> : null}
        </div>
        {profile.loading ? (
          <Spinner label="Loading snapshot history…" />
        ) : profile.error ? (
          <ErrorBanner message={profile.error} onRetry={loadProfile} />
        ) : snapshots.length === 0 ? (
          <p className="muted">
            No snapshots yet — run a tilt check to start building history.
          </p>
        ) : (
          <div className="profile-strip">
            <Sparkline points={sparkPoints} />
            <div className="profile-meta">
              <span className="muted">
                {snapshots.length} snapshot{snapshots.length === 1 ? "" : "s"} ·{" "}
                {sessions.length} coach session{sessions.length === 1 ? "" : "s"}
              </span>
              <span className="muted">
                Latest:{" "}
                {snapshots[0]
                  ? `${snapshots[0].tilt_score} (${snapshots[0].tilt_level})`
                  : "—"}
              </span>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
