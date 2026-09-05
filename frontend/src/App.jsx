import { lazy, Suspense, useEffect, useRef, useState } from "react";
import PlayerSearch from "./components/PlayerSearch.jsx";
import Backdrop from "./components/Backdrop.jsx";
import Dashboard from "./components/Dashboard.jsx";
import AnalysisTab from "./components/AnalysisTab.jsx";
import MentalCoachTab from "./components/MentalCoachTab.jsx";
import MetaTab from "./components/MetaTab.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import {
  playerKey,
  parseShareParams,
  buildShareUrl,
  parseRecentPlayers,
  addRecentPlayer,
} from "./utils.js";
import { track, trackSessionStart } from "./analytics.js";
import { useGSAP, revealIn, motionOK, canHover } from "./anim.js";

// Lazily loaded so gsap's SplitText + ScrambleTextPlugin stay out of the main
// chunk — the footer effect only ever runs on hover-capable devices anyway.
const ScrambledText = lazy(
  () => import("./components/reactbits/ScrambledText.jsx"),
);

const STORAGE_KEY = "vac:last-player";
const RECENT_KEY = "vac:recent-players";
const REPO_URL = "https://github.com/SergioB03/Valorant-ai-companion";

// Shareable URLs: ?player=Name%23TAG&region=eu&tab=analysis. Parsed once at
// load; URL params win over the saved-player fallback. A URL-supplied player
// deliberately does NOT overwrite localStorage — opening someone else's
// shared link shouldn't clobber your own saved player (that only happens when
// you actively search).
const INITIAL_SHARE = parseShareParams(
  typeof window !== "undefined" ? window.location.search : "",
);

const FOOTER_TEXT =
  "Powered by Claude + Henrik API. Not affiliated with or endorsed by Riot Games.";

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
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw);
    if (p && p.name && p.tag) {
      return { name: p.name, tag: p.tag, region: p.region || "na" };
    }
  } catch {
    /* corrupted storage — ignore */
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

export default function App() {
  const [player, setPlayer] = useState(
    () => INITIAL_SHARE.player || loadSavedPlayer(),
  );
  const [recent, setRecent] = useState(loadRecentPlayers);
  const [tab, setTab] = useState(INITIAL_SHARE.tab || "dashboard");
  const mountTracked = useRef(false);
  const mainRef = useRef(null);
  const tabRefs = useRef({});

  // Panels stay mounted and are toggled with [hidden], so on a tab change we
  // animate whichever panel just became visible. Cheap, and it keeps each tab's
  // internal state alive across switches. The [data-panel] marker is what makes
  // this reliable: a structural :scope selector used to match the keyed wrapper
  // div first, so MetaTab (the one panel outside it) never got its entrance.
  useGSAP(
    () => {
      const visible = mainRef.current?.querySelector(
        "[data-panel]:not([hidden])",
      );
      revealIn(visible, { y: 8, duration: 0.34 });
    },
    { scope: mainRef, dependencies: [tab] },
  );

  useEffect(() => {
    // Ref guard keeps StrictMode's dev double-mount from double-firing.
    if (mountTracked.current) return;
    mountTracked.current = true;
    trackSessionStart();
    track("page_view", { tab: "dashboard" });
  }, []);

  // Keep the address bar shareable and the title readable in a tab strip.
  // replaceState, not pushState — tab switches shouldn't pile history entries.
  // Privacy holds: analytics.js sends location.pathname only (never the query
  // string), so Riot IDs in the URL cannot leak into analytics events.
  useEffect(() => {
    try {
      window.history.replaceState(null, "", buildShareUrl(player, tab));
    } catch {
      /* history API blocked (e.g. sandboxed iframe) — non-fatal */
    }
    document.title = player
      ? `${player.name}#${player.tag} — Valorant AI Companion`
      : "Valorant AI Companion";
  }, [player, tab]);

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

  // Active searches (and recent-chip taps) only. Wave 2's demo sentinel must
  // never come through here — this writes real-player state (vac:last-player,
  // vac:recent-players). Riot IDs never go into analytics events either.
  function handleSearch(next) {
    setPlayer(next);
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
  }

  function clearRecent() {
    setRecent([]);
    try {
      localStorage.removeItem(RECENT_KEY);
    } catch {
      /* storage blocked — non-fatal */
    }
  }

  return (
    <div className="app">
      <Backdrop />
      <div className="top-glow" aria-hidden="true" />
      <header className="topbar">
        <div className="brand">
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
        </div>
        {/* Keyed so a recent-player chip tap re-seeds the form — PlayerSearch
            initializes its fields from `initial` on mount only. */}
        <PlayerSearch
          key={playerKey(player)}
          initial={player}
          onSearch={handleSearch}
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
        </p>
      ) : (
        /* Landing hero — mental-game positioning instead of the old
           "No player selected" dead end. Wave 2's demo-player CTA lands in
           this section. Game framing only: an AI coach, never therapy. */
        <section className="panel hero rise" aria-labelledby="hero-title">
          <h2 className="hero-title" id="hero-title">
            Mechanics only get you so far —{" "}
            <span>your mental gets you the rest of the way</span>
          </h2>
          <p className="hero-sub">
            Run a <strong>tilt check</strong> between queues — a 0–100 read of
            your last ten competitive matches: loss streaks, KDA and headshot
            dips, and the maps or agents that tilt you. Then talk it through
            with an <strong>AI mental coach</strong> that has seen those games,
            and get coach-style match analysis and meta answers on the side.
          </p>
          <p className="hero-cta muted">
            Enter a Riot ID above (in-game name plus #tag, e.g. Jett#1234),
            pick the account&apos;s region and hit Track. Free, no account —
            and not affiliated with or endorsed by Riot Games.
          </p>
        </section>
      )}

      {recent.length > 0 ? (
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
            // The visible label swaps with viewport width, and BOTH spans are
            // excluded from the accessible name at some size (one by
            // display:none, the other by aria-hidden) — which left these tabs
            // nameless to a screen reader on mobile. An explicit aria-label
            // pins the full, meaningful name at every width.
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
            outside the keyed wrapper so its Q&A state survives switches.
            Each panel gets its own ErrorBoundary: a crash in one tab leaves
            the shell and the other three usable. */}
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
              <MentalCoachTab player={player} active={tab === "mental"} />
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
            <MetaTab />
          </ErrorBoundary>
        </div>
      </main>

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
          <a href={REPO_URL} target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
        </nav>
      </footer>
    </div>
  );
}
