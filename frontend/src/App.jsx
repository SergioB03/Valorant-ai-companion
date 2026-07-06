import { useState } from "react";
import PlayerSearch from "./components/PlayerSearch.jsx";
import Dashboard from "./components/Dashboard.jsx";
import AnalysisTab from "./components/AnalysisTab.jsx";
import MentalCoachTab from "./components/MentalCoachTab.jsx";
import MetaTab from "./components/MetaTab.jsx";
import { playerKey } from "./utils.js";

const STORAGE_KEY = "vac:last-player";

const TABS = [
  { id: "dashboard", label: "Dashboard" },
  { id: "analysis", label: "Performance Analysis" },
  { id: "mental", label: "Mental Coach" },
  { id: "meta", label: "Meta Q&A" },
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
            className={`tab ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main>
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
        Powered by Claude + Henrik API. Not affiliated with or endorsed by Riot
        Games.
      </footer>
    </div>
  );
}
