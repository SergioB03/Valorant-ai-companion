# Valorant Ranked — Ranks, RR, MMR and Seasons

Snapshot from training data (late 2025 / early 2026). Riot tunes RR gains,
queue restrictions and season structure over time; verify specifics in-client.

## Rank ladder

From lowest to highest:

- Iron 1–3
- Bronze 1–3
- Silver 1–3
- Gold 1–3
- Platinum 1–3
- Diamond 1–3
- Ascendant 1–3 (added in 2022 to decompress the upper ladder)
- Immortal 1–3
- Radiant (top of the ladder, roughly the top 500 per region)

Each named rank has three tiers except Radiant. The majority of the player base
sits between Bronze and Gold.

## Ranked Rating (RR)

- Every tier spans 0–100 RR. Reaching 100 promotes you; dropping below 0 demotes
  you (you land partway up the lower tier, around 70 RR, and get some demotion
  protection).
- Typical gains/losses are about 10–30 RR per match, driven mostly by win/loss.
- Below Immortal, individual performance relative to expectation nudges RR;
  at Immortal+ it is almost purely win/loss and opponent strength.
- Wins against higher-MMR lobbies pay more; losses to lower-MMR lobbies cost more.

## MMR vs RR

- MMR is your hidden matchmaking rating — the system's true estimate of your skill.
  RR is the visible currency you grind.
- If your MMR is higher than your displayed rank, you gain more RR per win than
  you lose per loss, and the system accelerates you upward.
- Losing repeatedly at your MMR doesn't just cost RR — it lowers MMR, which
  quietly shrinks future gains. This is why tilt-queueing is doubly expensive.
- You are always matched by MMR, not by displayed rank; lobby rank spread is a
  rough proxy at best.

## Placements, acts and resets

- New (or returning) players play 5 placement matches to receive a rank.
- The competitive calendar is split into Acts (in 2025, Riot moved to a yearly
  "Season 25" structure with multiple short Acts, replacing the old
  Episode/Act naming — exact cadence may have shifted since).
- Act-to-act your rank carries over with a soft squish/reset and a short
  placement series; larger resets accompany the start of a new season year.
- Each Act awards an Act Rank badge based on your best wins that Act.

## Queue restrictions

- Parties of 2–3 must be within a limited rank spread of each other (roughly
  adjacent named ranks through most of the ladder).
- 5-stacks can queue together at almost any rank combination, but wide-spread
  5-stacks take a significant RR gain reduction.
- Immortal+ players face stricter party restrictions (mostly solo/duo, or
  5-stack with reduced RR) to protect ladder integrity.
- You must reach account level 20 before unlocking Competitive.

## Immortal and Radiant

- Immortal 1 starts at a regional RR threshold; from there, the leaderboard is
  the real rank — your RR number places you against everyone in the region.
- Radiant requires being at the very top of the regional leaderboard (top 500,
  with a minimum RR floor) and staying active.
- Leaderboard players have win/loss-dominated RR: dropping performance-based
  adjustments prevents stat-padding at the top.

## Premier

- Premier is the team-based competitive mode: you register a roster, play a
  weekly schedule of matches against teams in your division, and qualify for
  playoff tournaments at the end of each stage.
- Divisions ladder upward (Open → Intermediate → Advanced → Elite → Contender),
  and Premier is positioned as the path-to-pro pipeline feeding Challengers.
- Matches use a pick/ban style map selection and a more esports-like format
  than regular ranked.

## Practical climbing advice

- RR is noisy week to week; MMR trends over 50+ games are the honest signal.
- Duo with someone slightly better than you in a similar role — the MMR of the
  lobby rises, and wins pay more.
- Rank anxiety games (playing "not to lose") measurably lower win rate; if you
  notice RR-watching between rounds, that's a sign to take a break.
- One-tricking a role (not necessarily one agent) is the most consistent
  climbing strategy: your decision-making compounds.
