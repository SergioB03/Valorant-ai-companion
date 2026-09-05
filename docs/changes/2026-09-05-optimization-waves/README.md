# 2026-09-05 — Optimization waves 1–4

Baseline captured before implementing the four-wave optimization roadmap
(see [docs/OPTIMIZATION-PLAN.md](../../OPTIMIZATION-PLAN.md)).

## Before

- `before-desktop.png` — live https://rebuy.gg landing at 1440×900
- `before-mobile.png` — same at 390×844

Note: the animated map-splash backdrop is missing from the desktop capture — the ~5 MB
splash PNG had not finished downloading when headless Edge snapshotted the page. That
timing failure is itself part of the motivation for FE4 (self-hosted resized WebP assets).

## What is changing

- **Wave 1 (keystone):** merge `security/config-and-proxy-trust` (security headers, tests,
  health endpoints, CI running tests, durable budget counters), CI gates the deploy,
  outside-in uptime monitoring hooks, HenrikDev TTL cache, React ErrorBoundary,
  privacy-policy footer link.
- **Wave 2:** RAG gold-set retrieval eval + measured chunker fixes; frontend CI floor
  (ESLint + Vitest); self-hosted WebP splashes/icons (~20 MB → ~1.5 MB); shareable URLs
  + OG tags; restore drill + watchdogs + AWS cost guardrails.
- **Wave 3:** VALORANT Wiki patch-notes ingestion, two-tier answering + distance floor,
  SQLite answer cache, citation UX, full ARIA tabs + selector-bug fix, network
  discipline (timeouts/abort/cancel), backdrop paint hygiene.
- **Wave 4 (eval-gated):** BM25 hybrid + FlashRank rerank only if the wave-2 eval shows
  retrieval misses.

After screenshots will be added alongside these when the waves land.

## Landed

### rag

Everything measured against a new gold-set retrieval eval (RA2 first, per the mandated order):

- **Eval harness** — `backend/tests/eval/gold_set.json` (34 positives incl. the 4 MetaTab chips,
  7 negative probes) + `test_rag_eval.py` computing Hit@5 (section + source) and MRR@5 against the
  real Chroma index. Opt-in via `RUN_RAG_EVAL=1` (`tests/eval/conftest.py` un-stubs chromadb);
  excluded from the default suite. **Baseline: Hit@5 section 0.871, source 1.000, MRR@5 0.745.**
- **Chunker fixes (RA1)** — same-section-only merging, boundary-aware `_split_long` (no more
  mid-word cuts), preamble/disclaimer paragraphs de-indexed (they were outranking real content),
  contextual headers (`source § section`) embedded per chunk, `n_results` 5→8, front-matter
  parsing (`patch`/`date`). **→ 0.941 / 0.971 / 0.848.**
- **Patch ingestion (RA3 of the plan)** — `backend/scripts/ingest_patch_notes.py` (MediaWiki API →
  corpus markdown, CC BY-SA attribution, per-file patch/date front matter); ran it for 13.04 and
  13.05 and committed the files. Corpus is now current to patch 13.05 (2026-09-01), up from late 2025.
- **BM25 hybrid (RA8, gate opened)** — two lexical misses survived the chunker fixes, so rank-bm25
  + RRF fusion landed in `_retrieve`. **Final: Hit@5 section 1.000, source 1.000, MRR@5 0.794.**
  FlashRank not adopted (its gate — remaining misses — did not open); full decision table in
  docs/OPTIMIZATION-PLAN.md under RA8.
- **Two-tier answering (RA4)** — `_query` distances surfaced; `DISTANCE_FLOOR = 1.40` tuned on the
  gold set (positives ≤ 1.371, far-domain junk ≥ 1.433); floored questions get an explicit
  "Outside my notes:" model-knowledge answer instead of misleading chunks; system prompt now allows
  labelled general-knowledge fallback and carries the corpus-vintage + today's-date line.
- **Answer cache (RA5)** — `meta_answer_cache` in SQLite (exact-match on normalized question +
  corpus fingerprint `index_version()`; self-invalidating on any corpus/chunker change); measured
  cache hit ~2 ms vs ~3.6 s cold; also applied the INF8 `PRAGMA synchronous=NORMAL` to db.py.
- **Citation UX backend (RA6)** — `/meta/ask` gains optional `sources[i].used` (json_schema
  structured call with parse fallback to retrieval order) and top-level `corpus_vintage` (from
  patch front matter, never mtimes); `/meta/status` reports `corpus_vintage` too.
- **Request-path safety (RA7)** — `/meta/ask` no longer calls `ensure_index()`; a cheap latched
  `is_ready()` (non-blocking lock probe) answers 503 + `Retry-After: 15` while warming.
- **Tests** — 42 new unit tests (`test_rag_chunker.py`, `test_rag_answering.py`,
  `test_rag_meta_route.py`), all chroma/Claude-stubbed; suite 76 passed + 2 eval-skipped.

### frontend

All 8 plan items (FR1-FR8) plus the /meta/ask citation-UX consumption. Verified locally:
`eslint .` clean, `vitest --run` 28/28, `vite build` green; production build smoke-tested
via `vite preview` + headless Edge (`after-desktop.png`, `after-mobile.png`,
`after-share-url.png` — captured locally, pre-deploy).

- **FR1 Shareable URLs + OG tags** — `?player=Name%23TAG&region=xx&tab=...` parsed on load
  (URL wins over `vac:last-player`; region validated against the whitelist, bad tabs dropped),
  canonical URL kept via `history.replaceState`, `document.title` tracks the player. Static
  OG/twitter meta in index.html with a generated 1200×630 `public/og-card.png`
  (`scripts/make-og-card.mjs`, app-own branding). Privacy verified + spec'd: analytics sends
  `location.pathname` only, never the query string.
- **FR2 ErrorBoundary** — app-level wrap in main.jsx + one per tab panel; fallback reuses the
  ErrorBanner styling with Try again / Reload. Analytics gets only the boundary label, never
  the error message.
- **FR3 Privacy page** — `public/privacy.html` (design tokens inlined, no JS/analytics) +
  "Privacy & analytics" footer link. States endpoint-templates/anon-ids/referrer-host only,
  DNT fully honored, operator SQLite storage, and the `vac:vid` / `vac:last-player` /
  `vac:sid` clearing instructions. Closes the Aug-21 compliance item.
- **FR4 Self-hosted assets** — `scripts/fetch-assets.mjs` (sharp) emits 1920w q75 WebP
  splashes + 36/88px icon WebPs into `src/assets/` (~0.96 MB committed vs ~19.9 MB CDN
  originals). Backdrop + Insignia import them (Vite-fingerprinted → Caddy immutable cache);
  runtime fallback chain local → CDN → dot kept. `assetsInlineLimit: 0` so icons stay
  cacheable files instead of base64 bloat.
- **FR5 Tabs finished** — reveal-selector bug fixed with `[data-panel]:not([hidden])` (MetaTab
  gets its entrance again); full APG tabs pattern (ids, `aria-controls`, roving tabIndex,
  Arrow/Home/End with focus, `role=tabpanel` + `aria-labelledby` + `tabIndex=-1`);
  `role="log"` on the coach chat so replies/typing announce; contrast: placeholder
  `#5f6d7a → #8a97a4`, both 10px micro-type tokens → 11px; richer "no player" guidance line.
- **FR6 Paint hygiene** — backdrop mounts only current+previous layers (was: all six
  accumulate), faded layers pause kenburns, ticks skipped while `document.hidden`; pulse
  animations rebuilt as opacity-only overlays (`::after`), finite at 6 iterations —
  `pulseCard`/`pulseIns` box-shadow repaint loops removed; ScrambledText now `React.lazy`
  (19.7 kB split out; main chunk 263.79 kB, below the 272.81 kB baseline).
- **FR7 Network discipline** — `request()` gets a 60s `AbortSignal.timeout` (matched to the
  proxy window) merged with caller signals; Cancel buttons + 100ms Stopwatch + post-response
  "generated in X.Xs" chips on the three Claude waits (analyze, tilt check, meta ask); aborts
  surface as gentle "cancelled" notes, not errors, and skip analytics; Dashboard/coach-chat
  abort in flight on unmount/player switch; MentalCoach profile fetch now waits for first tab
  activation (removes a wasted request per search against /mental/profile's 15/min budget).
- **FR8 CI floor** — eslint (flat, js-recommended + react-hooks) + vitest as devDeps; exact
  `lint` and `test` script names for the CI wiring; specs for parseDate (incl. a hardened
  manual UTC parse of Henrik's prose format so Safari/iOS stops silently failing),
  stripMarkdown, splitParagraphs, the share-URL parser round-trip, and analytics
  queue/retry/cap/DNT behavior in jsdom (28 tests). Housekeeping: dead `frontend/vercel.json`
  deleted (README's repo-tree line still mentions it — README.md is outside frontend
  ownership), conflicting pre-grid mobile `.search` rules removed.
- **Citation UX (RAG interface)** — source chips are now tap-to-reveal buttons (snippet was
  hover-only `title`, invisible on touch); optional `used: true` renders a badge and dims
  unused sources; optional `corpus_vintage` renders a caption under the answer. All fields
  optional — current backend responses render unchanged.

### infra

IN2–IN8 landed in code; every AWS-side mutation is **scripted but deliberately not
executed** from this session (no AWS calls were made) — the exact pending steps are the
"Pre-deploy checklist" table in DEPLOYMENT.md.

- **CI gates the deploy (IN2)** — deploy.yml restructured: `deploy` now `needs:` three
  check jobs (`lint` ruff, `test` backend pytest, `frontend` npm ci/lint/test/build); a red
  suite can no longer ship. lint.yml keeps the identical jobs for pull requests. Post-deploy
  smoke test moved from `/api/` + `/api/meta/status` (200 even with missing keys) to
  `/api/health/ready` (503 exactly then), with the existing retry loop; deploy.sh's on-box
  wait now polls `/api/health`.
- **HenrikDev TTL cache (IN4)** — in-process dict cache in `riot_service._henrik_get`:
  account 10 min / matches 2 min, keyed on full URL + sorted params (any size/mode/region
  variance is a separate entry), 256-entry cap with expired-first eviction,
  `time.monotonic()` timestamps, errors never cached. Single-loop-safe by construction (no
  await between check and insert; uvicorn runs one process). 8 new tests in
  `backend/tests/test_riot_cache.py`; suite 84 passed + 2 eval-skipped.
- **Restore path (IN5)** — `infra/restore.sh`: newest-or-named S3 backup → integrity check +
  per-table row counts → `--drill` (temp dir, read-only, leaves evidence), `--target-dir`,
  or full on-box restore (pre-backup safety net, api stopped, stale `-wal`/`-shm` deleted so
  SQLite can't replay a mismatched WAL, timestamped keep of the old db, health-checked
  restart). bootstrap.sh's instance policy gains `s3:GetObject` on `companion/*` only.
  **Drill: pending — run `infra/restore.sh --drill`** (needs AWS access; blocked this session).
  DEPLOYMENT.md's ops table no longer teaches the torn-copy `compose cp` backup; it now has
  backup/restore/timer/rollback rows and the Litestream-deferred note.
- **Watchdogs (IN6)** — `infra/disk-watch.sh` + `vac-watchdog.timer` (written by deploy.sh,
  every 5 min): >85% root disk → Discord webhook (6 h re-alert damping), unhealthy compose
  service → restart + Discord. Compose api healthcheck now hits `/health` (dependency-free
  liveness) instead of `/`; `restart: unless-stopped` verified and documented as
  exit-only — the watchdog covers hung-but-alive. CloudWatch instance/system status alarms +
  SNS email + EC2 auto-recover: **scripted in `infra/ec2-alarms.sh`, pending execution.**
- **Money guardrails (IN7)** — `infra/cost-guardrails.sh` ($20/mo AWS Budget with 50/80%
  actual + 100% forecast emails; Cost Anomaly Detection service monitor + $5-threshold daily
  subscription): **scripted, pending execution.** Anthropic console spend cap documented as
  a user step (checklist item 6) — no API exists for it.
- **Outside-in alerting hooks (IN3)** — backup.sh pings `$HEALTHCHECK_URL` (or SSM
  `/vac/HEALTHCHECK_URL`) only after a successful upload (dead-man switch); healthchecks.io
  and UptimeRobot account creation documented as user steps (checklist items 7–8, including
  the never-bare-`/health` Caddy-fallback trap).
- **Production arming (IN1 follow-ups)** — `infra/arm-production.sh` creates
  `/vac/ENVIRONMENT=production` (env reaches the container via the existing SSM →
  `backend/.env` → compose `env_file` path — no compose change needed) and copies
  `/vac/RIOT_API_KEY` → `/vac/HENRIK_API_KEY` without deleting the old name: **scripted,
  pending execution**; the old parameter is deleted only after a verified deploy
  (post-deploy step in DEPLOYMENT.md).
- **Small hardening (IN8)** — compose: mem/cpu caps on both services (1g/1.5 api,
  256m/0.5 web on the 2 GB t3.small), `no-new-privileges` on both, `cap_drop: ALL` on api
  (uid 1000, high port), `read_only` rootfs + tmpfs `/config` `/data` `/tmp` on web (api
  stays writable: Chroma + backup staging). `.github/dependabot.yml`: weekly pip/npm/actions,
  grouped minor/patch so each ecosystem yields one PR. `dnf-automatic` (security-only,
  apply_updates=yes) in user-data.sh. Legacy `render.yaml` deleted (references were only in
  the docs updated here); DEPLOYMENT.md's Render/Vercel section rewritten as history of the
  real AWS path. README repo tree corrected (render.yaml/vercel.json gone; scripts/, tests/,
  infra/, docs/ added) and the backups roadmap item checked off.
  copilot-instructions.md screenshot convention aligned to `docs/changes/<date>-<slug>/`.
