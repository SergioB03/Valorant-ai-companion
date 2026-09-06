# 2026-09-05 — Landing page + Growth Waves 2–3

Fixes the owner-reported "always lands on my test user's dashboard" behavior (last-player
auto-restore hijacked the homescreen — which also hid the Wave-1 hero from returning
visitors) and finishes the council roadmap: real landing page, ⭐ demo player, friendly
quota state, shareable tilt card, returning-player ritual, patch-digest pages, plus the
tilt_snapshots bounding precondition and the dead RIOT_API_KEY fallback cleanup.

## Before

- `before-homescreen.png` / `before-mobile.png` — live rebuy.gg fresh-visit state
  (Wave-1 hero; returning visitors with a saved player skipped straight past this).

## Landed

### backend

- **Quota-header interface** (`app/deps.py`, `app/main.py`): the daily-allowance 429 now
  carries `X-Quota-Exhausted: 1` (the only signal the frontend keys the friendly state
  on — the per-minute and upstream 429s don't send it), `Retry-After` = seconds to UTC
  midnight, and `X-Quota-Limit`; successful AI responses carry `X-Quota-Limit` too (read
  from `FREE_AI_ACTIONS_PER_IP_PER_DAY`, never hardcoded; omitted when the quota is
  disabled). All three are CORS-exposed. Every AI-spending path (`/claude/analyze`,
  `/mental/tilt-check`, `/mental/coach`, `/meta/ask`) now answers `Cache-Control:
  no-store` on success *and* error, so CloudFront/browsers can never replay one caller's
  answer or quota headers to another. Pinned by `tests/test_quota_headers.py`.
- **tilt_snapshots bounded** (`app/db.py`) — the Wave-3 ritual precondition:
  `report_json` is no longer written (grep-verified nothing ever read it) and a
  one-time migration scrubs the blobs an existing database still holds; each riot_id is
  capped at `TILT_SNAPSHOTS_PER_PLAYER` (30) snapshots, oldest pruned in the same
  transaction as the insert; a `TILT_RETENTION_DAYS` (180) sweep piggybacks on the
  existing analytics-pruning cadence. Pinned by `tests/test_tilt_snapshots.py`.
- **Patch-digest pages** (`scripts/generate_patch_digest.py`): maintainer-run, offline,
  deterministic — no AI, no network, and deliberately no backend endpoint. Reads the
  `knowledge/patch-notes-<ver>.md` front matter + body and emits structural digests
  (section/agent/ability names + change counts, never the notes' text) as
  self-contained pages matching the app's design tokens (privacy.html pattern):
  `frontend/public/patch/13-04.html`, `13-05.html`, `index.html`, plus
  `frontend/public/sitemap.xml`. Every page carries CC BY-SA attribution, the wiki
  source URL, "not official Riot text", and the non-affiliation disclaimer, and links
  the official notes. Generated output committed; `tests/test_patch_digest.py` pins
  attribution + the never-reproduce property against the real corpus.
- **RIOT_API_KEY fallback removed** (`app/services/riot_service.py`,
  `app/routes/health.py`, `.env.example`): the SSM migration is complete and
  `/vac/RIOT_API_KEY` is deleted, so `HENRIK_API_KEY` is now the only name read —
  readiness no longer reports "configured" off a variable the client code ignores.
  `tests/test_health.py` re-pinned to the end state.
- Suite: 114 passed / 2 skipped (was 84 / 2), run via `backend/venv/Scripts/python.exe -m pytest`.

### frontend

- **The landing decision** (`App.jsx`, `utils.js resolveInitialPlayer`): routing is now
  URL param > same-session marker (`vac:session-player`, sessionStorage, written on
  every active selection) > landing page, always. `vac:last-player` / `vac:recent-players`
  no longer auto-load anything — they power the landing's "Jump back in" card and the
  search prefill only. The tab shell renders only once a player (or the demo) is active,
  and the brand mark is now a link home.
- **Landing page**: full-height hero on the Wave-1 copy (clamp-scaled display type),
  "See the demo" + "Track your Riot ID" (focuses the search) CTAs, a three-feature
  insignia-card showcase reusing the app's sentiment contract (Omen/tilt, Sage/coach,
  Cypher/knowledge base), the existing trust badge, and the "Jump back in" card:
  continue-as button, recent chips, and the Wave-3 ritual — time-based copy driven by
  the saved tilt report's timestamp, dismissible, at most once per session
  (`vac:ritual-shown`), one-tap "Run tilt check now" wired through a new `autoRun` prop
  (tap-only, never for URL players, never on mount/timer), soft-capped at 3 prompted
  checks/day (`vac:tilt-prompts`). CSS-only staggered entrances, all killed under
  prefers-reduced-motion; no new npm deps.
- **⭐ Demo player** (`api.js` + `src/demo-fixtures.js`): module-level demo flag
  short-circuits every endpoint against a dynamically-imported fixtures module
  (separate 6.9 kB chunk) — synthetic Demo#VAC account, 10 believable matches, a
  60/"heated" tilt report whose numbers are consistent with `detect_tilt`'s scoring
  (Omen pulse + 4 signals + trigger map), structured analysis with a tilt warning,
  canned coach exchange, profile sparkline, canned meta answer. Chat input disabled
  ("Track a real player to chat"), persistent "Sample data" chip + Exit demo, never
  written to last-player/recents/session marker or the report cache, share-URL
  `replaceState` suppressed, `demo_started` the only analytics event. Verified via
  headless-Chrome CDP: zero non-analytics requests, zero storage writes.
- **Quota-exhausted friendly state** (`api.js`, `common.jsx AIErrorNotice` +
  `AIQuotaCaption`): `err.quotaExhausted` / `err.retryAfterSeconds` lifted off the
  response headers, last-seen `X-Quota-Limit` remembered. Amber "Out of free AI actions
  today — resets at midnight UTC (about Nh from now)" notice with no Retry button, keyed
  ONLY on `X-Quota-Exhausted`; bare per-minute 429s get "slow down a moment" copy with
  Retry; "Uses 1 of your N free daily AI actions" caption near all three AI buttons
  (N from the header, never hardcoded; hidden in demo).
- **Shareable tilt card + Copy link** (`src/share-card.js`, `MentalCoachTab`): canvas
  renderer (fillText after `document.fonts.load`, no SVG-in-img, control/bidi/zero-width
  stripping + length caps on names), first-person framing + "AI estimate from public
  match data — rebuy.gg" + date, app branding only. Save image (guaranteed path) /
  gesture-scoped `ClipboardItem` copy / `navigator.share` on capable devices — offered
  only for the actively-selected (vac:last-player) player, never URL visits or demo.
  "Copy link" chips on the dashboard account card and the tilt-report header
  (`copy_link` event, tab only). `share_card` events carry method + ok, no identities.
- **Patch-digest links**: MetaTab ("Browse the patch digests") and the global footer
  link `/patch/`.
- **Privacy page**: documents `vac:session-player`, `vac:ritual-shown`,
  `vac:tilt-prompts`.
- Tests 78/78 (53 existing + 25 new: landing routing precedence incl. demo-sentinel
  rejection, demo short-circuit with mocked fetch, quota-header parsing, share-card
  sanitization, ritual copy + soft-cap helpers); eslint clean; build green (main chunk
  282 kB, demo fixtures split out). Flows verified end-to-end in headless Chrome:
  search → reload restore → landing ritual → autoRun (single request), URL-player
  isolation, quota state, mobile landing, share-card render.
