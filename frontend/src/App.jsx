import { useEffect, useRef, useState } from "react";
import PlayerSearch from "./components/PlayerSearch.jsx";
import Backdrop from "./components/Backdrop.jsx";
import Dashboard from "./components/Dashboard.jsx";
import AnalysisTab from "./components/AnalysisTab.jsx";
import MentalCoachTab from "./components/MentalCoachTab.jsx";
import MetaTab from "./components/MetaTab.jsx";
import { playerKey } from "./utils.js";
import { track, trackSessionStart } from "./analytics.js";
import { useGSAP, revealIn, motionOK, canHover } from "./anim.js";
import ScrambledText from "./components/reactbits/ScrambledText.jsx";

const STORAGE_KEY = "vac:last-player";

const FOOTER_TEXT =
  "Powered by Claude + Henrik API. Not affiliated with or endorsed by Riot Games.";

// `short` is shown on narrow screens. Without it "Performance Analysis" pushes
// the last two tabs off a phone screen — the bar scrolls, but nothing signals
// that, so half the app looked missing.
const TABS = [
  { id: "dashboard", label: "Dashboard", short: "Stats" },
  { id: "analysis", label: "Performance Analysis", short: "Analysis" },
  { id: "mental", label: "Mental Coach", short: "Coach" },
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

export default function App() {
  const [player, setPlayer] = useState(loadSavedPlayer);
  const [tab, setTab] = useState("dashboard");
  const mountTracked = useRef(false);
  const mainRef = useRef(null);

  // Panels stay mounted and are toggled with [hidden], so on a tab change we
  // animate whichever panel just became visible. Cheap, and it keeps each tab's
  // internal state alive across switches.
  useGSAP(
    () => {
      const visible = mainRef.current?.querySelector(
        ":scope > div > div:not([hidden]), :scope > div:not([hidden])",
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

  function handleTab(next) {
    if (next !== tab) track("tab_change", { tab: next });
    setTab(next);
  }

  function handleSearch(next) {
    setPlayer(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      /* storage full/blocked — non-fatal */
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
        <PlayerSearch initial={player} onSearch={handleSearch} />
      </header>

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
        <p className="tracking-line muted">
          No player selected — search a Riot ID above to get started.
        </p>
      )}

      <nav className="tabs" role="tablist" aria-label="Sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            // The visible label swaps with viewport width, and BOTH spans are
            // excluded from the accessible name at some size (one by
            // display:none, the other by aria-hidden) — which left these tabs
            // nameless to a screen reader on mobile. An explicit aria-label
            // pins the full, meaningful name at every width.
            aria-label={t.label}
            className={`tab ${tab === t.id ? "active" : ""}`}
            onClick={() => handleTab(t.id)}
          >
            <span className="tab-full">{t.label}</span>
            <span className="tab-short" aria-hidden="true">{t.short}</span>
          </button>
        ))}
      </nav>

      <main ref={mainRef}>
        {/* Player-scoped panels remount on player change; MetaTab lives
            outside the keyed wrapper so its Q&A state survives switches. */}
        <div key={playerKey(player)}>
          <div hidden={tab !== "dashboard"}>
            <Dashboard player={player} />
          </div>
          <div hidden={tab !== "analysis"}>
            <AnalysisTab player={player} />
          </div>
          <div hidden={tab !== "mental"}>
            <MentalCoachTab player={player} />
          </div>
        </div>
        <div hidden={tab !== "meta"}>
          <MetaTab />
        </div>
      </main>

      <footer className="footer">
        {/* React Bits' ScrambledText decodes the characters the cursor passes
            over. Purely decorative, so it's swapped for plain text under
            reduced motion — and the text reads identically either way. */}
        {motionOK() && canHover() ? (
          <ScrambledText radius={70} duration={0.9} speed={0.4} scrambleChars=".:">
            {FOOTER_TEXT}
          </ScrambledText>
        ) : (
          FOOTER_TEXT
        )}
      </footer>
    </div>
  );
}
