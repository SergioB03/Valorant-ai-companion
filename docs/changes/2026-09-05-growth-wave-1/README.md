# 2026-09-05 — Growth Wave 1

Implements the five Wave-1 quick wins from [docs/GROWTH-FEATURES.md](../../GROWTH-FEATURES.md)
(the council's staff-SWE-vetted specs, including all security mitigations as requirements):

1. Tappable starter prompts in coach chat (Meta-tab chip pattern, same send path)
2. Mental-game positioning: static hero in `index.html` + real empty state (demo CTA lands here in Wave 2)
3. Persist paid AI reports per player + "generated Xh ago" stamp (saves Claude spend; never chat messages)
4. GitHub footer link + "Open source · privacy-first" badge
5. Recent-players quick switcher (localStorage, capped, clearable)

## Before

- `before-landing.png` — live rebuy.gg landing: the "No player selected" dead end both
  analysts independently flagged as the #1 activation leak
- `before-mental-tab.png` — Mental Coach tab via deep link: inert example-question hint,
  no starter prompts, reports lost on every reload

After screenshots will be appended when the wave lands.

## Landed

All five items shipped, frontend-only (zero backend changes). Verified: `eslint .` clean,
`vitest run` 53/53 green (3 files), `npm run build` green.

**1. Tappable starter prompts in coach chat** — `MentalCoachTab.jsx`'s `sendMessage(e)` is now
`send(text)` plus a thin `handleChatSubmit(e)`; the inert `chat-hint` paragraph became three
`.chip-btn` starter chips (Meta-tab `EXAMPLES` pattern), rendered only while
`messages.length === 0` and `disabled={sending}`. Chips call the exact same `send()` as typed
messages, so the optimistic append, rollback-and-restore-to-input on failure, and the
`coach_message_sent` event behave identically. The AI disclosure stays above the chips.
Only new CSS is a tiny `.chat-starters` centering block.

**2. Mental-game positioning** — static `.boot-hero` markup inside `<div id="root">` in
`index.html` (README tagline + tilt-check/AI-mental-coach explainer, self-contained inline
`<style>`, crawler-visible, replaced wholesale by `createRoot` on mount — no hydration, no
build changes); meta/og/twitter descriptions now lead with "AI mental coach" + "tilt check
between queues"; the `App.jsx` "No player selected" line is a real hero section repeating that
copy (Wave 2's demo CTA lands there, per the code comment). Game framing only, no therapy
claims, no Riot marks, not-affiliated disclaimer kept. `TABS` reordered to put Mental Coach
second; the default tab is still `dashboard`, so `INITIAL_SHARE`, `buildShareUrl` and the ARIA
wiring needed no changes — `TAB_IDS` in `utils.js` and the panel DOM order were synced to match.
Reminder from the council: **set the Anthropic console monthly hard cap before any traffic push**
(operator action, not code).

**3. Persist paid AI reports per player** — new `src/reports.js` stores `{ result, at }` under
`vac:analysis:<playerKey>` / `vac:tilt:<playerKey>`; `AnalysisTab` and `MentalCoachTab` hydrate
in their `useState` initializers (App's keyed remount is the hydration trigger), write on
success, and render a mandatory "generated Xh ago" chip via `relativeDate(at)` beside the
existing GeneratedChip; Re-analyze / Run tilt check remain the refresh path. LRU cap of 6
players across both kinds, try/catch on all storage IO, shape validation on every read, no
analyze/tilt analytics on hydration, and an explicit code comment that coach chat messages are
never persisted. `privacy.html`'s key list updated in the same change.

**4. GitHub link + trust badge** — footer nav renamed `aria-label="About"` and gained a GitHub
link; a factual badge under the search ("Open source · privacy-first" → repo; "no accounts, no
cookies, DNT honored — details" → `/privacy.html`). All external links carry
`rel="noopener noreferrer"`. No Discord link (none exists — per the council's kill).

**5. Recent-players quick switcher** — `vac:recent-players` maintained in `handleSearch`
(dedupe by `playerKey`, unshift, cap 5, try/catch), rendered as an always-visible `.chips` row
under the tracking line with a one-tap "Clear recent" chip; no focus-dropdown. `PlayerSearch`
is keyed with `playerKey(player)` so the form re-seeds on chip tap. Entries are validated on
read like `loadSavedPlayer()` (pure `parseRecentPlayers`/`addRecentPlayer` in `utils.js`).
Riot IDs go into no analytics events (none were added). Wave 2's demo sentinel must not pass
through `handleSearch` — commented at the call site. `privacy.html` updated.

**Tests** — `src/reports.spec.js` (new, jsdom): save/load round trips, read validation against
tampered/corrupt entries, LRU eviction incl. recency refresh and corrupt-entry-first, and
blocked-storage tolerance. `src/utils.spec.js` extended: recent-players dedupe/cap/validate/
parse. Starter-prompt send-path equivalence is guaranteed by construction (one `send()`
function); no component-level test was added because the project has no React testing library
and adding one was out of scope for this wave.
