import { useState } from "react";

// Sentiment insignia system — game-flavored markers for good vs bad.
// Agent UUIDs verified 2026-07 against
// https://valorant-api.com/v1/agents?isPlayableCharacter=true
const AGENT_UUIDS = {
  gekko: "e370fa57-4757-3604-3648-499e1f642d3f",
  omen: "8e253930-4c05-31dd-1b6c-968525494517",
  brimstone: "9f0d8ba9-4140-b941-57d3-a7ad57c6b417",
  sage: "569fdd95-4d10-43ab-ca70-79becc718b46",
  cypher: "117ed9e3-49f3-6512-3ccf-0cada7e3823b",
};

// Shared contract:
//   strength / positive  -> Gekko,     green  #4ade80, soft glow
//   weakness / negative  -> Omen,      red    #ff4655, slow 2s pulse
//   tactical tip         -> Brimstone, amber  #facc15
//   mental / reset       -> Sage,      cyan   #7dd3fc
//   pattern / neutral    -> Cypher,    off-white
export const SENTIMENTS = {
  strength: { agent: "gekko", color: "#4ade80" },
  weakness: { agent: "omen", color: "#ff4655" },
  tip: { agent: "brimstone", color: "#facc15" },
  mental: { agent: "sage", color: "#7dd3fc" },
  neutral: { agent: "cypher", color: "#ece8e1" },
};

export function agentIcon(kind) {
  const s = SENTIMENTS[kind] || SENTIMENTS.neutral;
  return `https://media.valorant-api.com/agents/${AGENT_UUIDS[s.agent]}/displayicon.png`;
}

/**
 * Angled chip: agent icon + uppercase label. Falls back to a colored dot
 * if the icon fails to load.
 */
export function Insignia({ kind, label }) {
  const safeKind = kind in SENTIMENTS ? kind : "neutral";
  const [failed, setFailed] = useState(false);
  return (
    <span className={`insignia insignia-${safeKind}`}>
      {failed ? (
        <span className="insignia-dot" aria-hidden="true" />
      ) : (
        <img
          className="insignia-icon"
          src={agentIcon(safeKind)}
          alt=""
          loading="lazy"
          onError={() => setFailed(true)}
        />
      )}
      <span className="insignia-label">{label}</span>
    </span>
  );
}

/** Larger standalone agent portrait (comms avatars etc.) with dot fallback. */
export function AgentBadge({ kind, size = 44 }) {
  const safeKind = kind in SENTIMENTS ? kind : "neutral";
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <span
        className="insignia-dot insignia-dot-big"
        aria-hidden="true"
        style={{ background: SENTIMENTS[safeKind].color }}
      />
    );
  }
  return (
    <img
      src={agentIcon(safeKind)}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      style={{ objectFit: "contain", display: "block" }}
      onError={() => setFailed(true)}
    />
  );
}
