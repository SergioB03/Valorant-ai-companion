import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import PlayerSearch from "./components/PlayerSearch.jsx";
import Backdrop from "./components/Backdrop.jsx";
import Dashboard from "./components/Dashboard.jsx";
import AnalysisTab from "./components/AnalysisTab.jsx";
import MentalCoachTab from "./components/MentalCoachTab.jsx";
import MetaTab from "./components/MetaTab.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import { Insignia, AgentBadge } from "./components/Insignia.jsx";
import {
  DEMO_PLAYER,
  isDemoPlayer,
  playerKey,
  parseShareParams,
  buildShareUrl,
  parseRecentPlayers,
  parseStoredPlayer,
  addRecentPlayer,
  resolveInitialPlayer,
  tiltRitualCopy,
  promptedChecksToday,
  bumpPromptedChecks,
  utcDayKey,
  PROMPTED_TILT_CAP,
} from "./utils.js";
import { setDemoMode } from "./api.js";
import { loadReport } from "./reports.js";
import { track, trackSessionStart } from "./analytics.js";
import { useGSAP, revealIn, motionOK, canHover } from "./anim.js";

// Lazily loaded so gsap's SplitText + ScrambleTextPlugin stay out of the main
// chunk — the footer effect only ever runs on hover-capable devices anyway.
const ScrambledText = lazy(
  () => import("./components/reactbits/ScrambledText.jsx"),
);

const STORAGE_KEY = "vac:last-player";
const RECENT_KEY = "vac:recent-players";
// Same-session marker: set whenever a player is actively selected, so a
// mid-session reload restores the tracked view. Cleared when the tab closes
// (sessionStorage) — a fresh visit always gets the landing page.
const SESSION_KEY = "vac:session-player";
// Wave-3 ritual bookkeeping: the returning-player nudge shows at most once
// per browser session, and prompted one-tap checks are soft-capped per day.
const RITUAL_KEY = "vac:ritual-shown";
const PROMPTS_KEY = "vac:tilt-prompts";
const REPO_URL = "https://github.com/SergioB03/Valorant-ai-companion";

// Shareable URLs: ?player=Name%23TAG&region=eu&tab=analysis. Parsed once at
// load; URL params win over everything (explicit intent). A URL-supplied
// player deliberately does NOT overwrite localStorage — opening someone
// else's shared link shouldn't clobber your own saved player (that only
// happens when you actively search).
const INITIAL_SHARE = parseShareParams(
  typeof window !== "undefined" ? window.location.search : "",
);

// THE LANDING DECISION: URL param > same-session marker > landing, always.
// vac:last-player no longer auto-loads anything — it powers the landing's
// "Jump back in" card and the search prefill only.
const INITIAL_VIEW = resolveInitialPlayer(
  INITIAL_SHARE.player,
  (() => {
    try {
      return typeof window !== "undefined"
        ? sessionStorage.getItem(SESSION_KEY)
        : null;
    } catch {
      return null;
    }
  })(),
);

const FOOTER_TEXT =
  "Powered by Claude + Henrik API. Not affiliated with or endorsed by Riot Games.";

// The landing's three-feature showcase — same sentiment insignia contract as
// the reports themselves (Omen = the red flag, Sage = the reset, Cypher =
// the intel), so the landing previews the app's actual visual language.
const FEATURES = [
  {
    kind: "weakness",
    label: "Tilt radar",
    title: "Tilt check",
    body: "A 0–100 read of your last ten competitive matches — loss streaks, KDA and headshot dips, and the maps or agents that tilt you.",
  },
  {
    kind: "mental",
    label: "Reset protocol",
    title: "AI mental coach",
    body: "Talk it through with an AI coach that has seen those games. Honest, specific and game-framed — an AI, not a therapist.",
  },
  {
    kind: "neutral",
    label: "Knowledge base",
    title: "Meta Q&A",
    body: "Patch, agent and economy answers from a curated knowledge base that cites its sources — plus coach-style match analysis.",
  },
];

// `short` is shown on narrow screens. Without it "Performance Analysis" pushes
// the last two tabs off a phone screen — the bar scrolls, but nothing signals
// that, so half the app looked missing.
// Mental Coach sits right after Dashboard — it's the positioning pillar
// (see docs/GROWTH-FEATURES.md #2). The default tab is still "dashboard", so
// INITIAL_SHARE / buildShareUrl need no changes; utils.js TAB_IDS mirrors
// this order.
const TABS = [
  { id: "dashboard", label: "Dashboard", short: "Stats" },
  { id: "mental", label: "Mental Coach", short: "Coach" },
  { id: "analysis", label: "Performance Analysis", short: "Analysis" },
  { id: "meta", label: "Meta Q&A", short: "Meta" },
];

function loadSavedPlayer() {
  try {
    return parseStoredPlayer(localStorage.getItem(STORAGE_KEY));
  } catch {
    /* storage blocked — no saved player */
  }
  return null;
}

function loadRecentPlayers() {
  try {
    return parseRecentPlayers(localStorage.getItem(RECENT_KEY));
  } catch {
    /* storage blocked — start empty */
  }
  return [];
}

function canPromptTiltCheck() {
  try {
    return (
      promptedChecksToday(localStorage.getItem(PROMPTS_KEY), utcDayKey()) <
      PROMPTED_TILT_CAP
    );
  } catch {
    return false;
  }
}

export default function App() {
  const [player, setPlayer] = useState(INITIAL_VIEW.player);
  // Where the current player came from: "url" | "active" | "demo" | null.
  // URL players are read-only visits (no ritual, no share-card button).
  const [source, setSource] = useState(INITIAL_VIEW.source);
  const [demo, setDemo] = useState(false);
  const [lastPlayer, setLastPlayer] = useState(loadSavedPlayer);
  const [recent, setRecent] = useState(loadRecentPlayers);
  const [tab, setTab] = useState(INITIAL_SHARE.tab || "dashboard");
  // One-shot flag consumed by MentalCoachTab: set ONLY by the ritual's
  // explicit "Run tilt check" tap on the landing — never by mounts or timers.
  const [autoRunTilt, setAutoRunTilt] = useState(false);
  // The ritual nudge shows at most once per browser session.
  const [ritualAvailable, setRitualAvailable] = useState(() => {
    try {
      return !sessionStorage.getItem(RITUAL_KEY);
    } catch {
      return false;
    }
  });
  const mountTracked = useRef(false);
  const ritualShownRef = useRef(false);
  const mainRef = useRef(null);
  const tabRefs = useRef({});
  const searchNameRef = useRef(null);

  const showRitual = !player && ritualAvailable && lastPlayer != null;
  const showRitualCta = showRitual && canPromptTiltCheck();

  const lastTiltAt = useMemo(() => {
    if (!lastPlayer) return null;
    const saved = loadReport("tilt", playerKey(lastPlayer));
    return saved ? saved.at : null;
  }, [lastPlayer]);

  // Panels stay mounted and are toggled with [hidden], so on a tab change we
  // animate whichever panel just became visible. Cheap, and it keeps each tab's
  // internal state alive across switches. The [data-panel] marker is what makes
  // this reliable: a structural :scope selector used to match the keyed wrapper
  // div first, so MetaTab (the one panel outside it) never got its entrance.
  // `player` is a dependency too now that the shell mounts on player select.
  useGSAP(
    () => {
      const visible = mainRef.current?.querySelector(
        "[data-panel]:not([hidden])",
      );
      revealIn(visible, { y: 8, duration: 0.34 });
    },
    { scope: mainRef, dependencies: [tab, player] },
  );

  useEffect(() => {
    // Ref guard keeps StrictMode's dev double-mount from double-firing.
    if (mountTracked.current) return;
    mountTracked.current = true;
    trackSessionStart();
    track("page_view", { tab: "dashboard" });
  }, []);

  // Mark the ritual as consumed for this session as soon as it is shown
  // (the sessionStorage flag covers reloads), and retire it for this page
  // load once the user moves on to a player — but only if it was actually
  // shown. A session-restore load starts with a player active; the nudge is
  // still owed if they come back to the landing later this session.
  useEffect(() => {
    if (showRitual) {
      ritualShownRef.current = true;
      try {
        sessionStorage.setItem(RITUAL_KEY, "1");
      } catch {
        /* non-fatal — worst case the nudge shows again next load */
      }
    }
  }, [showRitual]);

  useEffect(() => {
    if (player && ritualShownRef.current) setRitualAvailable(false);
  }, [player]);

  // Keep the address bar shareable and the title readable in a tab strip.
  // replaceState, not pushState — tab switches shouldn't pile history entries.
  // Privacy holds: analytics.js sends location.pathname only (never the query
  // string), so Riot IDs in the URL cannot leak into analytics events.
  // Demo mode suppresses the share-URL write entirely: a copy-pasted
  // ?player=Demo%23VAC link would leak and burn Henrik quota on 404s.
  useEffect(() => {
    try {
      window.history.replaceState(
        null,
        "",
        demo ? "/" : buildShareUrl(player, tab),
      );
    } catch {
      /* history API blocked (e.g. sandboxed iframe) — non-fatal */
    }
    document.title = demo
      ? "Demo — Valorant AI Companion"
      : player
        ? `${player.name}#${player.tag} — Valorant AI Companion`
        : "Valorant AI Companion";
  }, [player, tab, demo]);

  function handleTab(next) {
    if (next !== tab) track("tab_change", { tab: next });
    setTab(next);
  }

  // WAI-ARIA tabs keyboard pattern: Left/Right cycle, Home/End jump. Selection
  // follows focus (automatic activation), and the roving tabIndex below keeps
  // exactly one tab in the page's tab order.
  function handleTabKeyDown(e) {
    const idx = TABS.findIndex((t) => t.id === tab);
    let next = null;
    if (e.key === "ArrowRight") next = (idx + 1) % TABS.length;
    else if (e.key === "ArrowLeft") next = (idx - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = TABS.length - 1;
    if (next == null) return;
    e.preventDefault();
    const id = TABS[next].id;
    handleTab(id);
    tabRefs.current[id]?.focus();
  }

  // Active searches (and recent/jump-back chip taps) only. This writes
  // real-player state (vac:last-player, vac:recent-players and the
  // same-session marker), so the demo sentinel must never come through here —
  // typing the demo identity just starts the demo instead. Riot IDs never go
  // into analytics events either.
  function handleSearch(next) {
    if (isDemoPlayer(next)) {
      startDemo();
      return;
    }
    setDemoMode(false);
    setDemo(false);
    setSource("active");
    setPlayer(next);
    setLastPlayer(next);
    const nextRecent = addRecentPlayer(recent, next);
    setRecent(nextRecent);
    try {
      localStorage.setItem(RECENT_KEY, JSON.stringify(nextRecent));
    } catch {
      /* storage full/blocked — non-fatal */
    }
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      /* storage full/blocked — non-fatal */
    }
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(next));
    } catch {
      /* storage full/blocked — non-fatal */
    }
  }

  // "Jump back in": one tap continues as a known player. With autoRun (the
  // ritual CTA) it also opens the Mental Coach tab and arms the one-shot
  // tilt check — still tap-initiated, and soft-capped per day.
  function continuePlayer(p, { autoRun = false } = {}) {
    track("continue_player", { ritual: autoRun });
    if (autoRun) {
      try {
        localStorage.setItem(
          PROMPTS_KEY,
          bumpPromptedChecks(localStorage.getItem(PROMPTS_KEY), utcDayKey()),
        );
      } catch {
        /* non-fatal — the cap just won't count this one */
      }
      setAutoRunTilt(true);
      handleTab("mental");
    }
    handleSearch(p);
  }

  // "See the demo": synthetic player, module-level api flag ON first so no
  // child can race a real request. Never written to vac:last-player /
  // vac:recent-players / the session marker; `demo_started` is the only
  // analytics event this fires.
  function startDemo() {
    setDemoMode(true);
    setDemo(true);
    setSource("demo");
    setPlayer({ ...DEMO_PLAYER });
    setTab("dashboard");
    setAutoRunTilt(false);
    track("demo_started");
  }

  // Back to the landing (brand click / Exit demo).
  function goHome() {
    setDemoMode(false);
    setDemo(false);
    setSource(null);
    setPlayer(null);
    setAutoRunTilt(false);
    try {
      sessionStorage.removeItem(SESSION_KEY);
    } catch {
      /* storage blocked — non-fatal */
    }
  }

  function focusSearch() {
    const el = searchNameRef.current;
    if (!el) return;
    try {
      el.focus({ preventScroll: true });
      el.scrollIntoView({
        block: "center",
        behavior: motionOK() ? "smooth" : "auto",
      });
    } catch {
      el.focus();
    }
  }

  function clearRecent() {
    setRecent([]);
    try {
      localStorage.removeItem(RECENT_KEY);
    } catch {
      /* storage blocked — non-fatal */
    }
  }

  // Search prefill comes from the saved player when there's nothing active
  // (and always in demo — the form should invite a real Riot ID, not Demo#VAC).
  const searchSeed = demo ? lastPlayer : player || lastPlayer;
  // Recents shown on the jump card, minus the player already on the big CTA.
  const otherRecent = recent.filter(
    (p) => !lastPlayer || playerKey(p) !== playerKey(lastPlayer),
  );

  return (
    <div className="app">
      <Backdrop />
      <div className="top-glow" aria-hidden="true" />
      <header className="topbar">
        <a
          className="brand"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            goHome();
          }}
          aria-label="Valorant AI Companion — home"
        >
          <svg
            className="brand-logo"
            viewBox="0 0 32 32"
            aria-hidden="true"
            focusable="false"
          >
            <path fill="#ff4655" d="M4 7l11 14h6L8 7H4zm24 0h-6l-7 9 3 4L28 7z" />
          </svg>
          <h1>
            Valorant <span>AI Companion</span>
          </h1>
        </a>
        {/* Keyed so a recent-player chip tap re-seeds the form — PlayerSearch
            initializes its fields from `initial` on mount only. */}
        <PlayerSearch
          key={playerKey(searchSeed)}
          initial={searchSeed}
          onSearch={handleSearch}
          nameRef={searchNameRef}
        />
      </header>

      {/* Factual trust badge — links the repo and the privacy page. */}
      <p className="trust-badge">
        <a
          className="trust-link"
          href={REPO_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open source · privacy-first
        </a>
        <span className="trust-note">
          no accounts, no cookies, DNT honored —{" "}
          <a href="/privacy.html">details</a>
        </span>
      </p>

      {player ? (
        <p className="tracking-line">
          Tracking{" "}
          <strong>
            {player.name}
            <span className="tag">#{player.tag}</span>
          </strong>{" "}
          <span className="region-chip">{player.region.toUpperCase()}</span>
          {demo ? (
            <>
              {" "}
              <span className="chip demo-chip">Sample data</span>{" "}
              <button
                type="button"
                className="chip chip-btn demo-exit"
                onClick={goHome}
              >
                Exit demo
              </button>
            </>
          ) : null}
        </p>
      ) : (
        /* ---------- LANDING ---------- Fresh visits always land here now:
           the saved player powers the "Jump back in" card instead of
           hijacking the homescreen. Game framing only: an AI coach, never
           therapy. */
        <div className="landing">
          <section className="landing-hero" aria-labelledby="hero-title">
            <h2 className="hero-title" id="hero-title">
              Mechanics only get you so far —{" "}
              <span>your mental gets you the rest of the way</span>
            </h2>
            <p className="hero-sub rise" style={{ animationDelay: "80ms" }}>
              Run a <strong>tilt check</strong> between queues — a 0–100 read of
              your last ten competitive matches: loss streaks, KDA and headshot
              dips, and the maps or agents that tilt you. Then talk it through
              with an <strong>AI mental coach</strong> that has seen those
              games, and get coach-style match analysis and meta answers on the
              side.
            </p>
            <div className="hero-actions rise" style={{ animationDelay: "160ms" }}>
              <button type="button" className="btn accent big" onClick={startDemo}>
                See the demo
              </button>
              <button type="button" className="btn ghost big" onClick={focusSearch}>
                Track your Riot ID
              </button>
            </div>
            <p className="hero-fine muted rise" style={{ animationDelay: "220ms" }}>
              Free, no account — just a Riot ID (in-game name plus #tag, e.g.
              Jett#1234). Not affiliated with or endorsed by Riot Games.
            </p>

            {lastPlayer || otherRecent.length > 0 ? (
              <section
                className="panel jump-card rise"
                style={{ animationDelay: "280ms" }}
                aria-labelledby="jump-title"
              >
                <div className="panel-head-row">
                  <h3 className="panel-title" id="jump-title">
                    Jump back in
                  </h3>
                  {showRitual ? (
                    <button
                      type="button"
                      className="btn ghost small"
                      onClick={() => setRitualAvailable(false)}
                    >
                      Dismiss
                    </button>
                  ) : null}
                </div>
                {showRitual ? (
                  <p className="panel-sub ritual-copy">
                    {tiltRitualCopy(lastTiltAt)}
                  </p>
                ) : null}
                <div className="jump-actions">
                  {lastPlayer ? (
                    <button
                      type="button"
                      className="btn accent"
                      onClick={() => continuePlayer(lastPlayer)}
                    >
                      Continue as {lastPlayer.name}
                      <span className="cta-tag">#{lastPlayer.tag}</span>
                    </button>
                  ) : null}
                  {showRitualCta && lastPlayer ? (
                    <button
                      type="button"
                      className="btn ghost"
                      onClick={() => continuePlayer(lastPlayer, { autoRun: true })}
                    >
                      Run tilt check now
                    </button>
                  ) : null}
                </div>
                {otherRecent.length > 0 ? (
                  <div
                    className="chips recent-row"
                    role="group"
                    aria-label="Recent players"
                  >
                    <span className="recent-label">Recent</span>
                    {otherRecent.map((p) => (
                      <button
                        key={playerKey(p)}
                        type="button"
                        className="chip chip-btn"
                        onClick={() => continuePlayer(p)}
                        aria-label={`Track ${p.name}#${p.tag} (${p.region.toUpperCase()})`}
                      >
                        {p.name}
                        <span className="tag">#{p.tag}</span>
                      </button>
                    ))}
                    <button
                      type="button"
                      className="chip chip-btn recent-clear"
                      onClick={clearRecent}
                    >
                      Clear recent
                    </button>
                  </div>
                ) : null}
              </section>
            ) : null}
          </section>

          <div className="feature-row" role="list" aria-label="What you get">
            {FEATURES.map((f, i) => (
              <article
                key={f.title}
                role="listitem"
                className={`feature-card kind-${f.kind} rise`}
                style={{ animationDelay: `${320 + i * 90}ms` }}
              >
                <div className="feature-head">
                  <span className="feature-avatar" aria-hidden="true">
                    <AgentBadge kind={f.kind} size={44} />
                  </span>
                  <h3 className="feature-title">{f.title}</h3>
                </div>
                <p className="feature-body">{f.body}</p>
                <Insignia kind={f.kind} label={f.label} />
              </article>
            ))}
          </div>
        </div>
      )}

      {player && recent.length > 0 ? (
        <div className="chips recent-row" role="group" aria-label="Recent players">
          <span className="recent-label">Recent</span>
          {recent.map((p) => (
            <button
              key={playerKey(p)}
              type="button"
              className="chip chip-btn"
              onClick={() => handleSearch(p)}
              aria-label={`Track ${p.name}#${p.tag} (${p.region.toUpperCase()})`}
            >
              {p.name}
              <span className="tag">#{p.tag}</span>
            </button>
          ))}
          <button
            type="button"
            className="chip chip-btn recent-clear"
            onClick={clearRecent}
          >
            Clear recent
          </button>
        </div>
      ) : null}

      {/* The tab shell renders only once a player (or the demo) is active —
          the landing above is the whole page until then. */}
      {player ? (
        <>
          <nav className="tabs" role="tablist" aria-label="Sections">
            {TABS.map((t) => (
              <button
                key={t.id}
                id={`tab-${t.id}`}
                ref={(el) => {
                  tabRefs.current[t.id] = el;
                }}
                role="tab"
                aria-selected={tab === t.id}
                aria-controls={`panel-${t.id}`}
                tabIndex={tab === t.id ? 0 : -1}
                // The visible label swaps with viewport width, and BOTH spans
                // are excluded from the accessible name at some size (one by
                // display:none, the other by aria-hidden) — which left these
                // tabs nameless to a screen reader on mobile. An explicit
                // aria-label pins the full, meaningful name at every width.
                aria-label={t.label}
                className={`tab ${tab === t.id ? "active" : ""}`}
                onClick={() => handleTab(t.id)}
                onKeyDown={handleTabKeyDown}
              >
                <span className="tab-full">{t.label}</span>
                <span className="tab-short" aria-hidden="true">{t.short}</span>
              </button>
            ))}
          </nav>

          <main ref={mainRef}>
            {/* Player-scoped panels remount on player change; MetaTab lives
                outside the keyed wrapper so its Q&A state survives switches
                (but resets crossing the demo boundary — a canned demo answer
                must not linger for a real player). Each panel gets its own
                ErrorBoundary: a crash in one tab leaves the shell and the
                other three usable. */}
            <div key={playerKey(player)}>
              <div
                data-panel=""
                role="tabpanel"
                id="panel-dashboard"
                aria-labelledby="tab-dashboard"
                tabIndex={-1}
                hidden={tab !== "dashboard"}
              >
                <ErrorBoundary label="The dashboard">
                  <Dashboard player={player} />
                </ErrorBoundary>
              </div>
              <div
                data-panel=""
                role="tabpanel"
                id="panel-mental"
                aria-labelledby="tab-mental"
                tabIndex={-1}
                hidden={tab !== "mental"}
              >
                <ErrorBoundary label="The mental coach">
                  <MentalCoachTab
                    player={player}
                    active={tab === "mental"}
                    autoRun={autoRunTilt}
                    onAutoRunDone={() => setAutoRunTilt(false)}
                    canShare={source === "active"}
                  />
                </ErrorBoundary>
              </div>
              <div
                data-panel=""
                role="tabpanel"
                id="panel-analysis"
                aria-labelledby="tab-analysis"
                tabIndex={-1}
                hidden={tab !== "analysis"}
              >
                <ErrorBoundary label="The performance analysis">
                  <AnalysisTab player={player} />
                </ErrorBoundary>
              </div>
            </div>
            <div
              data-panel=""
              role="tabpanel"
              id="panel-meta"
              aria-labelledby="tab-meta"
              tabIndex={-1}
              hidden={tab !== "meta"}
            >
              <ErrorBoundary label="The meta Q&A">
                <MetaTab key={demo ? "demo" : "live"} />
              </ErrorBoundary>
            </div>
          </main>
        </>
      ) : null}

      <footer className="footer">
        {/* React Bits' ScrambledText decodes the characters the cursor passes
            over. Purely decorative, so it's swapped for plain text under
            reduced motion — and the text reads identically either way. */}
        {motionOK() && canHover() ? (
          <Suspense fallback={FOOTER_TEXT}>
            <ScrambledText radius={70} duration={0.9} speed={0.4} scrambleChars=".:">
              {FOOTER_TEXT}
            </ScrambledText>
          </Suspense>
        ) : (
          FOOTER_TEXT
        )}
        <nav className="footer-links" aria-label="About">
          <a href="/privacy.html">Privacy &amp; analytics</a>
          <a href="/patch/">Patch digests</a>
          <a href={REPO_URL} target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
        </nav>
      </footer>
    </div>
  );
}
