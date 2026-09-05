# Growth Feature Council — 2026-09-05

Produced by a 7-agent council: a credential-free marketing analyst (live-site + competitor
research) and a UX analyst (popular-React-repo inspiration), each reviewed by a SWE-impact
and a cybersecurity reviewer, with a staff-SWE final pass that verified doubtful claims
against the code, killed/merged proposals, and ranked survivors. See docs/OPTIMIZATION-PLAN.md
for the same-day optimization waves this builds on.

All doubtful claims verified against the repo — every load-bearing correction in the reviews holds. Final output follows.

# Final Vetted Feature List — Valorant AI Companion

## Sanity-check results (repo-verified)

I checked every review claim that a decision hinges on. **All held:**

- `frontend/src/main.jsx:7` uses `ReactDOM.createRoot().render()` — the marketing pitch's "hydration" framing is wrong; the SWE's static-placeholder-in-`#root` shape is the correct one.
- `backend/app/services/mental_service.py` `detect_tilt` (line 30+) scores **only** loss_streak, kda_drop, hs_drop, low_win_rate, trigger_map, trigger_agent. **No chat-sentiment input exists.** The UX proposal's disclosure copy as pitched would be misinformation and would contradict the "no chat text analyzed/stored" privacy posture. The corrected input list is a hard requirement.
- `backend/app/routes/mental.py:97-107` — `/mental/coach` swallows a failed Henrik lookup (`raw = None`) and **still calls Claude**. A demo identity falling through to the network spends real money. Demo must never reach `api.js`.
- `frontend/src/components/common.jsx:26` — `EmptyState` takes only `title`/`body`; every tab's empty state is a verified dead end (`App.jsx:166-170`).
- `frontend/src/api.js:86-88` attaches `err.status` but nothing special-cases 429; and 429 is genuinely overloaded (daily quota, per-minute slowapi, Henrik upstream) — the "resets at midnight" copy on a bare 429 check would be wrong.
- `MetaTab.jsx:9,159-163` has clickable example chips; `MentalCoachTab.jsx:440` renders the same concept as an inert muted paragraph. Verified parity gap.
- `App.jsx` confirms: `vac:last-player` (line 19), URL players deliberately don't overwrite localStorage (comment, lines 21-25), keyed remount wrapper (line 205), `replaceState` share-URL effect (line 95), footer nav is `aria-label="Legal"` (line 270).

---

## Killed / trimmed (with reasons)

| Item | Verdict | Why |
|---|---|---|
| **Discord server/invite** (half of marketing #5) | **KILL** | No server exists; an empty Discord is negative social proof, and moderation is a standing commitment a solo student shouldn't take on as a side effect of a footer link. GitHub half survives. |
| **Live X-Quota-Remaining meter** (half of UX #3) | **KILL (for now)** | M effort + a per-caller oracle header with CDN-caching and shared-NAT confusion risks, for marginal value over the S-shaped fix. The exhausted-state + static caption delivers ~80%. |
| **Streak-aware banner copy** ("3 games tonight…") | **TRIM** | Requires state-lifting App↔Dashboard or extra Henrik calls against a 30/min key. V1 uses a localStorage last-check timestamp. |
| **Four-tab animated demo mode** | **TRIM** | The wow moment is dashboard + tilt report + canned coach opener. Full four-tab demo is the M/L shape with little extra conversion value. |
| **Backend endpoint for demo or patch-digest generation** | **KILL** | Both are static-file problems. Any live-generation path is an unauthenticated AI-spend surface — the exact open-relay shape SECURITY.md #2 already paid for once. |
| **"Chat sentiment" in tilt disclosure copy** | **KILL** | Factually false (verified above) and implies chat is analyzed/retained. |

No whole proposal died: all 12 collapse into 9 survivors after merging.

---

## Merges

1. **Demo player** — marketing #2 + UX #1 are the same feature. Merged below. ⭐
2. **Positioning hero + empty-state CTA** — marketing #1 and the empty-state halves of both demo pitches merge into one landing/empty-state overhaul; the demo button becomes its CTA.
3. **Share card + copy-link affordance** — marketing #3 absorbs the SWE's "Copy link" companion note (deep links currently have zero UI affordance).

---

## ⭐ Convergence flags (strong signal)

- **Demo player**: both analysts proposed it independently, from different evidence (funnel doctrine vs. competitor positioning). Highest-confidence bet on the list.
- **The dead-end empty state is the #1 activation leak**: both analyses independently identified the "No player selected" wall as the top funnel problem, just with different fixes (positioning copy vs. demo CTA) — which is why those fixes are merged and sequenced first.
- **Shipped deep links are invisible**: both tracks noted the share infrastructure just shipped with no UI affordance anywhere.

---

## Survivors, ranked by user-value-per-effort

### Wave 1 — quick wins (all frontend-only, each ≤ a day)

**1. Tappable starter prompts in coach chat — Effort: S**
Refactor `MentalCoachTab.jsx` `sendMessage(e)` into `send(text)` + a thin submit handler; replace the inert `chat-hint` paragraph (line 440) with `.chip-btn` buttons copying `MetaTab.jsx`'s EXAMPLES pattern verbatim, rendered only when `messages.length === 0`, `disabled={sending}`. Requirements: chips route through the same `send()` path so the optimistic-rollback error handling (restore text to input on failure) and `coach_message_sent` analytics behave identically to typed messages; the AI-disclosure notice stays above the chips. ~25 lines, zero new styles, zero backend. Best value-per-effort on the list.

**2. Mental-game positioning: static hero + empty-state overhaul — Effort: S**
Put the README tagline and a three-line tilt-score/mental-coach explainer as **static markup inside `<div id="root">`** in `frontend/index.html` (crawlers and link previews index it; React's `createRoot` swaps it out on mount — no hydration, no build changes; keep its styling self-contained via a tiny inline `<style>` so class drift can't silently break it), and rewrite the meta/og descriptions to lead with the mental angle. Replace the `App.jsx` "No player selected" line with a real hero/empty-state repeating that copy — this section is where Wave 2's demo button lands. Reorder `TABS` to move Mental Coach up; if the default tab changes, sync all three spots (`INITIAL_SHARE.tab || "dashboard"`, the `tab !== "dashboard"` omission in `buildShareUrl`, ARIA wiring). Requirements: no Riot marks; "AI mental coach" not "mental coach"; game-framing ("tilt check between queues"), never therapy/mental-health claims; keep the not-affiliated disclaimer. **Precondition for any traffic push: set the Anthropic console monthly hard cap — it's the only spend control no bug can defeat, and it's still pending.**

**3. Persist paid AI reports per player + "generated 2h ago" stamp — Effort: S**
Hydrate `AnalysisTab` result and `MentalCoachTab` tilt report from `localStorage` (`vac:analysis:<playerKey>` / `vac:tilt:<playerKey>`) in the `useState` initializer — the keyed remount at `App.jsx:205` becomes the hydration trigger; write `{result, at}` on success; render `relativeDate(at)` beside the existing GeneratedChip, keep "Re-analyze" as the refresh path. Requirements: the timestamp chip is mandatory (stale-data integrity); **never persist coach chat messages** (explicit code comment); LRU cap ~5-8 players, try/catch on all storage IO, validate shape on read; don't fire analyze/tilt analytics on hydration (natural implementation already avoids it); update `privacy.html`'s key enumeration in the same PR. Directly saves Claude spend under the $5/day breaker — the only feature here that pays for itself.

**4. GitHub link + "Open source · privacy-first" badge — Effort: S**
GitHub repo link in the footer (rename the `aria-label="Legal"` nav or add a sibling), plus a small badge near the search linking to the repo and `/privacy.html`. Requirements: `rel="noopener noreferrer"`; badge text factual and scoped ("no accounts, no cookies, DNT honored — details") rather than "we collect nothing"; no Discord link until a live server exists. An hour of work; makes the repo and site feed each other's credibility for the first time.

**5. Recent-players quick switcher — Effort: S**
Maintain `vac:recent-players` (dedupe by `playerKey`, unshift, cap 5, try/catch) in `handleSearch`; render as an always-visible `.chips` row under the tracking line — **skip the focus-dropdown** (blur/race/combobox-ARIA cost for zero value). Requirements: key `PlayerSearch` with `playerKey(player)` so the form syncs on chip tap (it initializes state from `initial` on mount only — verified); validate entries on parse like `loadSavedPlayer()`; a one-tap "clear recent" affordance; exclude the demo sentinel; update `privacy.html`; never put names in analytics events.

### Wave 2 — the conversion features

**6. ⭐ Demo player (merged) — Effort: M**
"See the demo" button on the new empty state loads a **synthetic** player via a module-level demo flag in `api.js` that short-circuits every call against a fixtures map keyed by endpoint template (~30 lines + one dynamically-imported fixtures module: account card, ~10 match summaries, one analysis JSON, one tilt report, coach opener) — fixtures generated once offline. Hard requirements (security + verified code paths): demo **never reaches the network** — `/mental/coach` spends Claude money even on failed lookups (verified), so the chat input is disabled with "track a real player to chat"; identity is clearly fake and unclaimable, UI stamped with a persistent "Sample data" chip and the AI-disclosure carried into the canned exchange; never written to `vac:last-player`; suppress the `replaceState` share-URL write in demo mode (else `?player=Demo%23VAC` links leak and burn Henrik quota on 404s); fire `demo_started` instead of `player_search`/funnel events. Add the `action` prop to `EmptyState` and export the module-private `CommsCard`/`SignalList`/`TrendPair` from `MentalCoachTab.jsx` as needed.

**7. Quota-exhausted friendly state + honest cost caption — Effort: S**
Backend: `deps.py ai_quota` raises its 429 with `X-Quota-Exhausted: 1` and `Retry-After` (seconds to UTC midnight); one-line `expose_headers` addition in CORS. Frontend: `api.js` reads the marker into `err.quotaExhausted`; tabs render an amber "Out of free AI actions today — resets at midnight UTC" notice **without a Retry button**; a static caption near the three AI buttons ("Uses 1 of your free daily AI actions"). Requirements: key the friendly copy on the header, **never on `status === 429` alone** (three different 429s exist — verified); per-minute 429s get "slow down a moment" copy; don't hardcode "40" (env-configurable — carry the number in the header or reuse the backend detail string); `Cache-Control: no-store` on AI-spending responses, verified against CloudFront, before any per-caller header ships.

**8. Shareable tilt-score card (client-side PNG) + copy-link — Effort: M**
New `share-card.js` canvas renderer + "Share my tilt check" button in `MentalCoachTab`'s report block, transposing the OG card's visual language from `make-og-card.mjs`; delivery via `canvas.toBlob` → download, `ClipboardItem` (constructed inside the gesture for Safari), `navigator.share` on mobile — Download is the guaranteed path. Requirements: draw text with `ctx.fillText` after `document.fonts.load(...)` — **no SVG-in-`<img>` intermediate** (fonts silently fall back) and no HTML/SVG templating of user strings (injection surface); cap/sanitize name length; first-person framing ("My tilt check") + "AI estimate from public match data — rebuy.gg" + date on the card; offer the button **only for the `vac:last-player` player**, not URL-supplied ones (anti-dunk speed bump); app branding only, no Riot marks; share analytics event carries no identity. Ship the trivial "Copy link" button alongside — the deep links currently have zero UI affordance.

### Wave 3 — retention & acquisition surfaces (each has a precondition)

**9. "Tilt check between queues" returning-player ritual — Effort: S code + M precondition**
Dismissible banner on load for a **saved-player restore only** (never a `?player=` share visit — `App.jsx` already distinguishes them), with time-based copy from a localStorage last-check timestamp and a one-tap "Run tilt check" CTA wired via an `autoRun` prop on `MentalCoachTab` (it already takes `active`). Hard requirements: the check fires **only on explicit tap** — never on mount, timer, or for URL players; banner shows at most once per session; client-side soft cap on prompted checks. **Precondition before shipping the habit loop**: bound `tilt_snapshots` (per-riot_id cap and/or retention window, stop persisting full `report_json`) — this feature deliberately multiplies the dataset that is the project's largest open Riot-policy exposure, so shrink it first. Watch `claude_spend` after launch; success here means higher daily burn by design.

**10. Public patch-digest page per patch — Effort: M first page, S per patch**
Static `frontend/public/patch/<ver>.html` (the `privacy.html` → dist → CloudFront pattern is proven end-to-end; zero infra changes), linked from MetaTab and the hero, plus `sitemap.xml` and per-page meta/OG. Generation is a **maintainer-run offline script** beside `ingest_patch_notes.py` — never a backend endpoint — with human review before commit (handles injection, hallucination, and over-quotation at once). Requirements: CC BY-SA attribution + source URL + "not official Riot text" on every page (front matter already carries the data); summarize and link to Riot's notes, never reproduce them; keep the disclaimer; pages cacheable at CloudFront. **Validate first**: hand-write digest #1 with no script, post it once, and only build the automation if it draws any search/Reddit traction.

---

## Suggested build order

Wave 1 is ~a focused week and moves activation, retention, trust, and real dollar savings with zero new attack surface. Ship the Anthropic monthly hard cap before item 2 goes live, and hold any Reddit/community push until the demo player (item 6) exists — positioning that attracts visitors into a dead-end empty state wastes the one first impression per visitor you get.