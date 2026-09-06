// Synthetic data for the demo player (Wave 2). Dynamically imported by
// api.js only when demo mode is on, so none of this ships in the main chunk.
//
// The identity is clearly fake and unclaimable (Demo#VAC), and the numbers
// are internally consistent with backend/app/services/mental_service.py's
// scoring so the demo doesn't lie about how the product works:
//   loss streak 3 (+25, high) + KDA -46% vs baseline (+20, medium)
//   + HS% -28% vs baseline (+10, low) + one trigger map (+5) = 60 → "heated"
// — which is exactly the state that shows off the Omen pulse, the signal
// list and the coach's read.
//
// Every function returns fresh objects: callers mutate API responses freely.

const HOUR = 3_600_000;
const DAY = 24 * HOUR;

export function demoAccount() {
  return {
    data: {
      puuid: "demo-fixture",
      region: "na",
      account_level: 128,
      name: "Demo",
      tag: "VAC",
      // No card art: the dashboard renders fine without it, and the demo
      // must not depend on (or hotlink) any external image.
      card: {},
    },
  };
}

// Newest first, like /riot/matches. 5W/5L over ten competitive games with a
// cold streak on top — a believable "rough night" for a Diamond player.
const MATCHES = [
  { map: "Ascent", agent: "Jett", kills: 9, deaths: 16, assists: 4, hs: 17, won: false, tier: "Diamond 1", ago: 2 * HOUR },
  { map: "Icebox", agent: "Reyna", kills: 12, deaths: 17, assists: 2, hs: 16, won: false, tier: "Diamond 1", ago: 3 * HOUR },
  { map: "Bind", agent: "Jett", kills: 11, deaths: 15, assists: 6, hs: 21, won: false, tier: "Diamond 1", ago: 4 * HOUR },
  { map: "Haven", agent: "Omen", kills: 18, deaths: 12, assists: 9, hs: 26, won: true, tier: "Diamond 1", ago: DAY + 2 * HOUR },
  { map: "Icebox", agent: "Jett", kills: 13, deaths: 16, assists: 3, hs: 22, won: false, tier: "Diamond 1", ago: DAY + 3 * HOUR },
  { map: "Split", agent: "Jett", kills: 21, deaths: 14, assists: 5, hs: 27, won: true, tier: "Diamond 1", ago: DAY + 5 * HOUR },
  { map: "Lotus", agent: "Omen", kills: 16, deaths: 11, assists: 8, hs: 24, won: true, tier: "Platinum 3", ago: 2 * DAY + 1 * HOUR },
  { map: "Ascent", agent: "Sova", kills: 10, deaths: 14, assists: 7, hs: 23, won: true, tier: "Platinum 3", ago: 2 * DAY + 3 * HOUR },
  { map: "Haven", agent: "Jett", kills: 24, deaths: 13, assists: 4, hs: 30, won: true, tier: "Platinum 3", ago: 2 * DAY + 4 * HOUR },
  { map: "Bind", agent: "Jett", kills: 14, deaths: 16, assists: 5, hs: 22, won: false, tier: "Platinum 3", ago: 3 * DAY + 2 * HOUR },
];

export function demoMatches(size = 10) {
  const now = Date.now();
  return MATCHES.slice(0, Math.max(1, size)).map((m, i) => ({
    match_id: `demo-${i + 1}`,
    map: m.map,
    mode: "Competitive",
    started_at: now - m.ago,
    agent: m.agent,
    tier: m.tier,
    kills: m.kills,
    deaths: m.deaths,
    assists: m.assists,
    headshot_percent: m.hs,
    score: m.kills * 250 + m.assists * 75,
    won: m.won,
  }));
}

export function demoAnalysis() {
  return {
    analysis: {
      overview:
        "You're a Jett-heavy entry player with real firepower when the game is going your way — the Haven and Split wins show clean opening duels and a 27-30% headshot rate. Tonight is a different story: three straight losses with your KDA nearly cut in half and your crosshair discipline slipping. The pattern reads like forcing the same aggressive angles after they've stopped working, especially on Icebox where both games got away from you.",
      strengths: [
        "When you win the opening duel your teams convert — 5 of your wins came off strong first bloods on aggressive entries.",
        "Your Omen games are quietly excellent: 2.2 KDA across both, playing for picks instead of forcing them.",
        "Baseline aim is legit — a 25% headshot rate over the older seven games is above the curve for your rank.",
      ],
      weaknesses: [
        "The last three games show classic tilt aim: 17% headshots vs your 25% baseline, spraying through smokes instead of resetting.",
        "Icebox is a problem map right now — 0 for 2, and both losses feature low-impact entries into stacked sites.",
        "You keep re-queueing immediately after losses; the drop-off between game one and game three tonight is steep.",
      ],
      tilt_warning:
        "Three losses in a row with falling KDA and headshot numbers — the classic tilt signature. The next queue is statistically your worst of the night.",
      tip: "Next game, take Omen instead of Jett and give yourself one full buy round before any aggressive peek — let the game come to you for the first three rounds.",
    },
    match_count: 10,
  };
}

export function demoTiltReport() {
  return {
    riot_id: "demo#vac",
    matches_analyzed: 10,
    tilt_score: 60,
    tilt_level: "heated",
    current_loss_streak: 3,
    signals: [
      { type: "loss_streak", severity: "high", detail: "3 losses in a row" },
      {
        type: "kda_drop",
        severity: "medium",
        detail: "KDA down 46% vs baseline (0.92 vs 1.69)",
      },
      {
        type: "hs_drop",
        severity: "low",
        detail: "Headshot% down 28% vs baseline (18.0% vs 24.9%)",
      },
      { type: "trigger_map", severity: "low", detail: "0 wins on: Icebox" },
    ],
    kda_trend: { recent: 0.92, baseline: 1.69 },
    hs_trend: { recent: 18.0, baseline: 24.9 },
    triggers: { maps: ["Icebox"], agents: [] },
    recommendation: "Take a 30-minute break before your next queue.",
    coach_message:
      "Three queues, three losses, and your numbers tell me exactly where your head is: KDA nearly halved and your headshot rate down ten points from baseline — that's not your aim disappearing, that's you forcing fights on tilt. The good news is the older games show a genuinely strong player, especially those Omen rounds where you played patient and let picks come to you. Here's the move: step away for thirty minutes, water, walk, anything off-screen. If you queue again tonight, lock Omen, and give yourself three rounds of deliberate, boring defaults before you take a single aggressive duel.",
  };
}

// The canned chat exchange shown in the demo's coach panel. The chat input
// itself is disabled in demo mode — this is display-only sample data.
export function demoChatSeed() {
  return [
    {
      role: "user",
      text: "That Ascent game tilted me hard. Should I keep queueing tonight?",
    },
    {
      role: "coach",
      text:
        "Honest answer? Not yet. You're on a three-loss streak and your recent KDA is 0.92 against a 1.69 baseline — every stat says the next game is your worst one of the night, not your redemption arc. Take the 30 minutes. When you come back, your first queue is a reset game: Omen, defaults, no hero peeks before round four. You've got the aim — the older games prove it. What you need right now is distance from the last loss, not another one.",
      tiltScore: 60,
      tiltLevel: "heated",
    },
  ];
}

// Defensive fixture: the demo UI disables chat entirely, but if anything
// ever calls coachChat in demo mode it gets this instead of the network.
export function demoCoachReply() {
  return {
    reply:
      "This is the sample coach — track a real player to have an actual conversation. The demo chat above shows what a session looks like.",
    tilt_score: 60,
    tilt_level: "heated",
  };
}

function sqliteUtc(msAgo) {
  return new Date(Date.now() - msAgo).toISOString().slice(0, 19).replace("T", " ");
}

export function demoProfile() {
  // Newest first, like /mental/profile. Trend math (mean of newest 3 vs
  // oldest 3: 49.7 vs 34.7) reads as "worsening" — consistent with the
  // heated report above.
  const points = [
    { score: 60, level: "heated", ago: 2 * HOUR },
    { score: 48, level: "warming", ago: DAY },
    { score: 41, level: "warming", ago: 2 * DAY },
    { score: 44, level: "warming", ago: 3 * DAY },
    { score: 32, level: "warming", ago: 5 * DAY },
    { score: 28, level: "warming", ago: 6 * DAY },
  ];
  return {
    riot_id: "demo#vac",
    snapshots: points.map((p) => ({
      tilt_score: p.score,
      tilt_level: p.level,
      matches_analyzed: 10,
      created_at: sqliteUtc(p.ago),
    })),
    sessions: [
      { created_at: sqliteUtc(2 * HOUR) },
      { created_at: sqliteUtc(DAY) },
      { created_at: sqliteUtc(4 * DAY) },
    ],
    trend: "worsening",
  };
}

export function demoMetaAnswer() {
  return {
    // Kept as explicit short paragraphs: splitParagraphs re-chunks anything
    // over ~320 chars on sentence boundaries, and "Patch 13.05" reads as a
    // sentence end to that regex.
    answer:
      "The most recent patches shook up the duelist meta. Patch 13.05 trimmed Jett's dash window and reduced Reyna's dismiss speed, pushing entry play toward more coordinated executes — and initiator flashes got slightly cheaper, so Gekko and Sova stocks are up in ranked.\n\nPatch 13.04's map rotation brought Icebox back into competitive queue, and its B site rework rewards slower, util-heavy takes. If you're climbing right now, controllers and initiators are the reliable picks; pure-aim duelist queues are punished harder than last act.\n\n(Demo answer — canned sample data, not generated live.)",
    sources: [
      {
        source: "patch-notes-13.05",
        section: "Agent updates",
        snippet:
          "Jett — Tailwind activation window reduced. Reyna — Dismiss movement speed reduced. Gekko — Wingman cost decreased",
        used: true,
      },
      {
        source: "patch-notes-13.04",
        section: "Map updates",
        snippet:
          "Icebox returns to the competitive map pool with a reworked B site intended to open additional attacker options",
        used: true,
      },
      {
        source: "ranked-guide",
        section: "Climbing fundamentals",
        snippet:
          "Agent comfort beats meta chasing below Ascendant — but role balance still decides close games",
        used: false,
      },
    ],
    corpus_vintage: "Patch 13.05",
  };
}
