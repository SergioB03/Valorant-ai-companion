# Optimization Plan — 2026-09-05

Produced by a 16-agent research/analysis pass (per-track code reader + web researcher, synthesis,
adversarial critique, revision, cross-track integration). Frontend inspiration drawn from Outline,
Bruno, and Excalidraw. Every recommendation was verified against the code at commit 8491da5.

## Track: frontend

The frontend is a disciplined 22-file plain-JSX React 18 + Vite SPA with a coherent hand-rolled Valorant design system, uniformly strong loading/error/empty states (MetaTab already ships clickable example-question chips), and end-to-end reduced-motion support — the craft floor is high. Its dominant real cost is decorative media: ~20 MB of full-res map splashes and 512-px agent icons hotlinked from a fan CDN, plus perpetual box-shadow paint loops and six accumulated will-change backdrop layers. The remaining gaps are surgical: a verified selector bug that leaves the Meta tab with no entrance animation, a half-finished ARIA tabs pattern, a coach chat that is silent to screen readers, no fetch timeout/abort/error-boundary anywhere, no shareable URLs or OG tags, no privacy-policy link despite localStorage visitor-id analytics, and zero frontend CI. Everything below elevates the existing design language in plain JS — no rewrite, no TS migration.

### FR1. Shareable URLs with OG tags: player and tab in the query string
**Impact:** high · **Effort:** S

Player identity lives only in localStorage (App.jsx:28-40), so any shared link lands on the empty search screen. On load, parse ?player=Name%23TAG&region=eu&tab=analysis (URL params win over the vac:last-player fallback); on handleSearch and handleTab (App.jsx:69-81), history.replaceState the canonical URL. Validate the region param against the REGIONS whitelist and encode with encodeURIComponent. ~30 lines in App.jsx plus a small parser in utils.js — no router needed for a 4-tab SPA, and Caddy's try_files fallback already serves index.html for any path. Pair it with what makes the link worth sharing: static og:title/og:site_name/og:description/og:image + twitter:card meta in index.html (verified: only a name=description exists today), using the app's own non-Riot branding, plus document.title updates with the tracked player. Without OG tags Discord unfurls a bare URL and the growth-loop premise collapses. Privacy holds: analytics.js sends location.pathname only (never the query string) and referrer host only, so Riot IDs cannot leak into analytics.

*Why:* The audience is Gen-Z gamers who live in Discord — 'drop your dashboard link in the server' is the app's most natural growth loop and it currently cannot happen. Riot IDs in a URL are user-initiated sharing of already-public identifiers. Highest delight-per-line-of-code in the plan, and a strong portfolio demo moment: send an interviewer a link that opens on a live analysis with a proper unfurl card.

*Inspiration:* outline/outline useBuildTheme.ts (UI state in URL params habit); critic's OG-unfurl addition, verified against index.html

*Files:* `C:\Users\sergi\Valorant-ai-companion\frontend\src\App.jsx`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\utils.js`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\components\PlayerSearch.jsx`, `C:\Users\sergi\Valorant-ai-companion\frontend\index.html`

### FR2. App-level React ErrorBoundary so one render error cannot blank the SPA
**Impact:** medium · **Effort:** S

Verified: main.jsx:6-10 renders <App /> bare, so a single render error in any component white-screens the entire live site with no recovery. Add a ~20-line class ErrorBoundary (componentDidCatch + fallback UI reusing the existing ErrorBanner styling from common.jsx, with a 'Reload' button styled from the current design tokens) and wrap <App /> in main.jsx; optionally wrap each of the four tab panels so a crash in one tab leaves the shell and other tabs usable. Plain JS, zero dependencies, no design change.

*Why:* This is the cheapest resilience win in the codebase: the app is live at rebuy.gg and renders data from two external APIs plus LLM output — exactly the kind of unexpected-shape input that throws mid-render. It also pairs naturally with the CI recommendation's goal of guarding error paths, and a graceful failure screen is itself a portfolio signal.

*Inspiration:* Critic's missing-item, verified against main.jsx

*Files:* `C:\Users\sergi\Valorant-ai-companion\frontend\src\main.jsx`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\components\ErrorBoundary.jsx (new)`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\App.jsx`

### FR3. Privacy-policy footer link: close the maintainer's own open compliance item
**Impact:** medium · **Effort:** S

Verified: no privacy link exists anywhere in frontend/src, the footer (App.jsx:159-170) renders only the non-affiliation FOOTER_TEXT, and analytics.js keeps a persistent anonymous visitor id in localStorage (vac:vid, line 11) while honoring DNT (navigator.doNotTrack check at line 22). Add a small footer link to a short static privacy page (a route-less modal or a plain /privacy.html in frontend/public) stating plainly: what is collected (endpoint templates, anonymous visitor/session ids, referrer host — never Riot IDs or query strings), that DNT is honored, that data stays in the operator's SQLite, and how to clear the localStorage ids. Style it as a Valorant-cut panel from existing tokens.

*Why:* The Aug 21 compliance review lists the privacy policy as still open, and shipping analytics with a persistent visitor id and no policy is the kind of gap that reads badly in a portfolio review. Near-zero effort, closes a real (not cosmetic) gap, and the honest DNT/no-PII story is already true in the code — it just needs to be stated.

*Inspiration:* Critic's missing-item, verified against App.jsx footer, analytics.js, and the Aug 21 compliance notes

*Files:* `C:\Users\sergi\Valorant-ai-companion\frontend\src\App.jsx`, `C:\Users\sergi\Valorant-ai-companion\frontend\public\privacy.html (new)`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\index.css`

### FR4. Self-host resized WebP splashes and insignia icons
**Impact:** high · **Effort:** M

One-time script (sharp or squoosh CLI) downloads the 6 map splashes and 5 agent icons, resizes to ~1920w quality-75 WebP for splashes (~150-250 KB each vs 2-5.4 MB) and 36px + 88px WebP for icons (2x the 18px chip in index.css:563-566 and 44px AgentBadge), committed under frontend\src\assets\maps\ and frontend\src\assets\agents\. Import them in Backdrop.jsx (replacing the splash() URL builder at lines 16-17) and Insignia.jsx (replacing agentIcon() at line 30) so Vite fingerprints them into /assets — which means the Caddyfile's existing immutable 1-year cache rule (lines 23-27) applies automatically. Total page weight drops from ~20 MB of images to ~1.5 MB, and core UI semantics (the sentiment insignia contract) stop depending on a third-party fan CDN's uptime. Same Riot fan-content assets already in use, so no new ToS exposure; keep the non-affiliation footer as-is.

*Why:* Measured 17,757,601 bytes of splash PNGs + 2,197,571 bytes of icons is the single largest cost in the app by an order of magnitude — on phones (which the Aug 25 mobile pass otherwise serves well) this is the difference between a snappy companion and a data-plan hog. Verified upstream offers no smaller variant (displayiconsmall.png returns 404), so self-hosting is the only fix, and committing ~1.5 MB of assets is fine for a hobby repo.

*Inspiration:* Measurement-driven (HEAD requests against media.valorant-api.com); Excalidraw's lean-precache philosophy for immutable assets

*Files:* `C:\Users\sergi\Valorant-ai-companion\frontend\src\components\Backdrop.jsx`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\components\Insignia.jsx`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\assets\ (new)`

### FR5. Finish the tabs: selector bug fix, full ARIA pattern, chat live region, contrast
**Impact:** high · **Effort:** M

One PR over the same App.jsx tab structure. (1) Fix the verified reveal bug: App.jsx:53-55's ':scope > div > div:not([hidden]), :scope > div:not([hidden])' always matches the keyed wrapper first in document order, so revealIn animates the wrapper and MetaTab — the only panel outside it — gets zero entrance, contradicting the comment at lines 48-50. Add data-panel to the four toggled divs (App.jsx:144-155) and query '[data-panel]:not([hidden])'; ~10 lines, flows through the existing motionOK() gate. (Skip the per-visit animation latch — per-switch entrance is the code's documented intent, so changing it is an optional taste call, not a fix.) (2) Complete what commit ff0a909 started (its comment at App.jsx:125-129 confirms the narrow scope): id + aria-controls per tab button, roving tabIndex, ArrowLeft/ArrowRight/Home/End handling, and role=tabpanel + aria-labelledby + tabIndex=-1 on the panels — this also delivers the only keyboard affordance this 4-tab app actually needs. (3) MentalCoachTab.jsx: role="log" on the .chat-messages container (~line 347) so coach replies and the typing indicator (lines 373-377) are announced — the app's only async-into-existing-view content. (4) index.css: raise placeholder #5f6d7a (~3.5:1, below AA) to ~#8a97a4; bump the 10px micro-type at lines 587 and 1040 to 11px. While in App.jsx, fold one sentence of guidance into the bare 'No player selected' line (114-116).

*Why:* The Meta tab is the only panel with zero entrance motion — the exact opposite of the intended polish — and screen-reader users currently hear 'tab, 1 of 4' while arrow keys do nothing and the flagship coach feature is completely silent to assistive tech. All verified gaps; standard APG work that elevates rather than replaces the design.

*Inspiration:* WAI-ARIA APG tabs pattern; outline/outline Fade.tsx for the selector-fix shape

*Files:* `C:\Users\sergi\Valorant-ai-companion\frontend\src\App.jsx`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\components\MentalCoachTab.jsx`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\index.css`

### FR6. Stop paying for invisible pixels: backdrop hygiene, finite pulses, lazy footer
**Impact:** medium · **Effort:** S

Three paired fixes to the decorative layer, sequenced after the self-hosting rec so wins are measured against local assets. (1) Backdrop.jsx: cap mounted layers to current + previous instead of accumulating all six (the shown array at lines 25/37 only ever grows — the 2.4s crossfade needs two layers plus the existing Image() preload), add '.backdrop-layer:not(.on) { animation-play-state: paused }' so faded-out layers stop running kenburns with will-change (index.css:81-94), and skip the setInterval tick when document.hidden — justified as skipping pointless state churn and decode work in background tabs (the CDN's max-age=1209600 plus browser timer throttling mean nothing re-downloads, so this is hygiene, not bandwidth). (2) Replace the infinite pulseCard/pulseIns border-color + box-shadow keyframes (index.css:522-541, 617-629) with an opacity pulse on a compositable ::after overlay, or settle after 3 iterations — AnalysisTab.jsx:28-31 attaches .pulse to every weakness item, so a 5-weakness report runs 6+ perpetual repaint loops today. (3) React.lazy the ScrambledText import (App.jsx:11) behind the existing motionOK() && canHover() gate with the plain-text footer as fallback — honestly scoped: only SplitText + ScrambleTextPlugin split out of the 272.81 kB main chunk; gsap core stays because anim.js needs it everywhere. No edits to the vendored file, respecting the README contract.

*Why:* Six full-viewport will-change layers cost ~50 MB GPU memory at 1080p, and box-shadow animation cannot be composited, so it is continuous main-thread paint on the exact low-end phones the mobile pass targets. All three fixes are invisible to the design — the theme looks identical, it just stops burning battery.

*Inspiration:* Outline's habit of gating every animation; Excalidraw's chunk-splitting of decorative code

*Files:* `C:\Users\sergi\Valorant-ai-companion\frontend\src\components\Backdrop.jsx`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\index.css`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\App.jsx`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\components\AnalysisTab.jsx`

### FR7. Network discipline plus honest waits: timeouts, aborts, Cancel, stopwatch
**Impact:** medium · **Effort:** M

api.js:12-27 has no timeout or abort anywhere. Add to request(): a default AbortSignal.timeout (15s for HenrikDev routes, 90s for Claude routes matching the advertised 'up to a minute') merged via AbortSignal.any with an optional caller-supplied signal, mapping AbortError to a friendly retryable message. Thread signals through: AnalysisTab gets a Cancel button next to 'Analyzing…' (the button is currently stuck disabled forever on a stall, ~line 198) — with the honest caveat that a client-side abort recovers the UI but does not halt backend Claude spend on an in-flight generation. Components abort in-flight requests on unmount/player-switch, which also supersedes the missing aliveRef guard in AnalysisTab (its sibling MentalCoachTab.jsx:121-128 has one). Make MentalCoachTab fetch getMentalProfile on first activation via an active={tab === 'mental'} prop instead of on mount while [hidden] (lines 130-145) — framed correctly: /mental/profile is SQLite-only (verified: no HenrikDev calls in backend/app/routes/mental.py), so this removes a wasted request per search against that route's own 15/min slowapi budget, not HenrikDev quota. Finally, the same three Claude-backed waits get a ~30-line Stopwatch.jsx (100ms tick, '4.7s' format, fixed width so the ticking number never nudges layout, React.memo) plus a post-response 'generated in 8.2s' chip reusing the existing .chip style — a live counter turns the app's longest dead time into visible progress. (The draft's useDeferredLoading hook is cut: fast paths already render skeletons, not spinners, and every actual Spinner sits on a multi-second Claude call.)

*Why:* A stalled Claude call currently bricks the Analyze button with no recovery path short of a reload, and player switches leak in-flight requests. Timeouts, Cancel, and the elapsed stopwatch are one coherent package over the same three waiting states — the reliability-and-trust layer for the app's slowest, most valuable feature.

*Inspiration:* usebruno/bruno ResponseStopWatch component (MIT, plain JS)

*Files:* `C:\Users\sergi\Valorant-ai-companion\frontend\src\api.js`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\components\AnalysisTab.jsx`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\components\MentalCoachTab.jsx`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\components\MetaTab.jsx`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\components\Stopwatch.jsx (new)`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\App.jsx`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\components\Dashboard.jsx`

### FR8. Frontend CI floor: ESLint + first Vitest specs wired into lint.yml
**Impact:** medium · **Effort:** M

package.json has only dev/build/preview scripts and lint.yml runs ruff on backend/app exclusively — 15 JS/JSX files are unguarded against the exact undefined-name-in-error-path bug class lint.yml's own comment describes. Add eslint (flat config: js.configs.recommended + react-hooks plugin) and vitest as devDependencies, lint and test scripts, and a small frontend job in .github/workflows/lint.yml (npm ci + npm run lint + npm test, ~40s). First specs are pure functions needing no DOM: utils.js parseDate, stripMarkdown, splitParagraphs. parseDate deserves special attention (verified utils.js:36-38): Henrik's prose format falls through to implementation-defined new Date('June 21, 2025 6:23 PM UTC') parsing with a silent raw-string fallback, and Safari has historically rejected such formats — meaning iOS users may quietly see unparsed date strings; pin the current behavior in specs and consider a hardened manual parse of the prose path. In the same PR, do the manual housekeeping (not linter-driven): delete the dead vercel.json and resolve the conflicting pre-grid mobile rules (index.css:1595-1602 vs 1535-1545). Coordinate with the unmerged origin/security/config-and-proxy-trust branch, which already adds a CI test step to the same workflow file — land whichever merges first and rebase the other. Optionally add JSDoc @typedef blocks for API response shapes in api.js — free IDE checking, and the honest answer to 'should this be TypeScript' (no, not at 22 files).

*Why:* Every other recommendation in this plan adds JS that nothing currently guards; a 40-second CI job is the difference between a portfolio that says 'I ship' and one that says 'I ship safely'. Deliberately minimal — no Prettier bikeshed, no coverage thresholds, no TS migration.

*Inspiration:* usebruno/bruno colocated *.spec.js habit; critic's parseDate/Safari missing-item, verified against utils.js

*Files:* `C:\Users\sergi\Valorant-ai-companion\frontend\package.json`, `C:\Users\sergi\Valorant-ai-companion\frontend\eslint.config.js (new)`, `C:\Users\sergi\Valorant-ai-companion\.github\workflows\lint.yml`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\utils.js`, `C:\Users\sergi\Valorant-ai-companion\frontend\src\index.css`, `C:\Users\sergi\Valorant-ai-companion\frontend\vercel.json (delete)`

## Track: rag

The RAG pipeline (9 markdown docs -> heading-aware chunker -> ChromaDB/MiniLM -> top-5 -> claude-opus-4-8) is operationally solid — index baked into the Docker image at build, layered spend controls on /meta/ask, graceful 503 UX — but its problems are quality, not plumbing, and every one below is now verified against the live code and index rather than hypothesized. Measured chunker defects bury gold content (5 cross-section merges, hard mid-word cuts at piece[:limit], 9 filename-labeled preamble chunks), and a live probe shows the 'reconstructed from training data' disclaimer preamble ranking #1 for the UI's own example chip while the gold chunk misses top-5 entirely. The corpus is a late-2025 snapshot while the live game is on patch 13.05 (Sept 2026), with no vintage disclosure in the UI, in the system prompt, or to Claude. There is no retrieval eval (main has no tests directory at all), so tuning is currently vibes; at 74 chunks / ~10K tokens changes are cheap to test, which makes measurement, honest disclosure, and write-ups the highest-value work — note the draft's Chroma-native hybrid-search rec was verified broken (sparse indexing is Chroma Cloud-only in chromadb 1.5.9 and Bm25EmbeddingFunction requires fastembed) and is demoted to eval-gated in-process work.

### RA1. Fix the measured chunker defects, embed contextual headers, and de-index the disclaimer boilerplate
**Impact:** high · **Effort:** S

Five changes, all in C:/Users/sergi/Valorant-ai-companion/backend/app/services/rag_service.py, all taking effect at the next deploy via the build-time re-embed (Dockerfile bakes the index): (1) make the merge step (lines 76-85) only merge chunks sharing the same section, or retitle when sections differ — today a <200-char chunk is glued under the PREVIOUS section's label, destroying 5 section labels corpus-wide (e.g. the agents meta-sentiment chunk labeled 'Sentinels', which is why the example chip 'Which agents are strong in ranked right now?' never retrieves its gold chunk); (2) in _split_long (lines 34-53), replace the hard piece[:limit] cut with a sentence/paragraph-boundary cut and prepend the section heading to continuation pieces (Tejo's kit tail starts mid-word with no 'Tejo' to embed-match); (3) give preamble chunks a real section name like 'Overview' instead of seeding heading with the filename (line 57), killing the 9 degenerate 'agents-meta.md > agents-meta.md' citation chips; (4) in _ingest (line ~105), embed documents as f"{source} § {section}\n\n{text}" — contextual-retrieval-lite; (5) NEW (verified live this session): stop indexing the repeated 'Snapshot from training data...' disclaimer paragraphs that open ranked-system.md, maps.md, economy.md, agents-meta.md, and patch-notes-recent.md — strip them at ingest (they become metadata/vintage info, not embedded text), because the agents-meta.md disclaimer preamble currently ranks #1 (distance 1.084) for the ranked-agents example chip, outranking all real content in a 74-chunk index. While in _query, bump n_results from 5 to 8 — at ~525 chars/chunk the extra 3 chunks cost fractions of a cent and mechanically raise recall.

*Why:* These are the only retrieval failures actually measured, and one was reproduced live during this review: gold content buried under wrong labels, kit chunks unfindable by their agent's name, citation chips that lie, and boilerplate disclaimers winning top-5 slots. All fixes are one file, zero ongoing cost, zero new dependencies.

*Inspiration:* Anthropic — Introducing Contextual Retrieval (contextual embeddings, applied without the paid LLM-context variant)

*Files:* `backend/app/services/rag_service.py`

### RA2. Build a gold-set retrieval eval — with negative probes and a cached CI model — before tuning anything else
**Impact:** high · **Effort:** S

Add C:/Users/sergi/Valorant-ai-companion/backend/tests/test_retrieval_eval.py plus a checked-in gold_set.json of ~30 real questions (start with the 4 MetaTab.jsx example chips and the 16 probe questions already run, mapped to expected (source, section) pairs). The test calls rag_service._query directly — zero Claude calls, zero spend — asserts Hit@5 above a floor and prints MRR@5. Two additions from review: (a) include NEGATIVE cases — wrong-game (CS2/LoL), far-domain junk, and current-patch questions the corpus cannot answer — asserting the distance-floor/refusal/fallback behavior of the two-tier rec, which otherwise ships unmeasured (critical because a measured legitimate hit at 1.345 sits within 0.06 of the draft's proposed 1.4 floor); (b) in CI, cache ~/.cache/chroma with actions/cache, or the ~80MB MiniLM ONNX model re-downloads every run and the 'runs in seconds' eval becomes the slowest, flakiest step. Main has no tests directory, so this rides on merging origin/security/config-and-proxy-trust (verified: it adds conftest.py, pytest deps, and CI test runs) — that merge is the infra-track precondition. Add 2-3 questions per ingested patch going forward.

*Why:* Every other recommendation here (chunker fixes, floor, deferred hybrid/reranker, model A/B) needs a pass/fail signal or it is guesswork; at 74 chunks the eval costs nothing. It is also the single best interview artifact this track can produce: 'I measured Hit@5 before and after each change' beats any amount of architecture.

*Inspiration:* Label Your Data 2026 RAG-eval roundup (Hit@5/MRR small-gold-set pattern, pytest-style)

*Files:* `backend/tests/test_retrieval_eval.py`, `backend/tests/gold_set.json`, `.github/workflows/lint.yml`

### RA3. Patch-notes ingestion from the VALORANT Wiki — commit-and-deploy, no new prod plumbing
**Impact:** high · **Effort:** M

Add C:/Users/sergi/Valorant-ai-companion/backend/scripts/fetch_patch_notes.py hitting the live-verified MediaWiki API (wiki.playvalorant.com/api.php?action=parse&page=Patch_Notes/13.05&prop=wikitext — confirmed MediaWiki 1.45.3, CC BY-SA 3.0, with 13.05 dated Sept 1 2026), the only structured patch-notes feed that exists (HenrikDev, valorant-api.com, and playvalorant.com verified to have none). The script must convert wikitext '== ==' headings to '## ' so chunk_markdown works unchanged and strip templates like {{PatchNav}}/{{Infobox}}, writing backend/data/knowledge/patch-notes-13-05.md with a CC-BY-SA attribution line and an explicit 'community-sourced summary, not official Riot text' header (Riot fan-content ToS). Since _ingest is generic across files, carry per-file {'patch': '13.05', 'date': '2026-09-01'} metadata via front-matter or filename parsing in chunk_markdown/_ingest — this metadata is also what the vintage-disclosure recs consume. Workflow: run locally once per patch (~every 2 weeks), review the output, commit, push — the existing deploy re-embeds at build, so production plumbing changes not at all. Retire the reconstructed 2025 summaries in patch-notes-recent.md once two real patches are in; defer systemd-timer automation until the manual run survives a few patches of wikitext edge cases.

*Why:* Staleness is the app's number-one quality problem — the corpus ends in late 2025, the live game is on 13.05, and the first example chip literally asks about recent patches. No retrieval tuning beats a year of missing content, and commit-and-deploy keeps ops at one reviewed script run per patch on a solo-maintainer budget.

*Inspiration:* VALORANT Wiki MediaWiki API (live-verified); AustinFWK/valorant-news-bot as proof no cleaner feed exists

*Files:* `backend/scripts/fetch_patch_notes.py`, `backend/data/knowledge/`, `backend/app/services/rag_service.py`

### RA4. Two-tier answering with a gold-set-tuned distance floor — and tell Claude the corpus's vintage
**Impact:** medium · **Effort:** S

Three changes in C:/Users/sergi/Valorant-ai-companion/backend/app/services/rag_service.py: (1) rewrite META_SYSTEM_PROMPT (lines 153-160) from 'ONLY the provided context' to 'prefer the context and cite it; when it does not cover the question, answer from general knowledge but explicitly label that part as outside the knowledge base and possibly outdated' — opus-4-8's early-2026 cutoff knows months of Valorant the 2025 corpus doesn't, and today users get stonewalled on exactly the current-patch questions the UI invites; (2) NEW (verified: no vintage anywhere in the current prompt): inject one line — 'Knowledge base snapshot: patch X / date Y; today is {date}' — sourced from the patch metadata of the ingestion rec or a hand-maintained constant, so Claude self-caveats staleness in every answer; the cheapest honesty fix in the track; (3) have _query return distances (Chroma computes them; ask_meta currently discards them) and, when the best hit exceeds a floor, tell Claude the KB found nothing relevant instead of injecting misleading chunks — but the floor MUST be tuned on the gold set's negative cases before shipping, not hardcoded: a measured legitimate hit (1.345) sits within 0.06 of the draft's proposed 1.4. Be honest in code comments and the README that the floor only catches far-domain junk — near-domain wrong-game questions (CS2 Mirage smokes at ~0.79-0.99) score CLOSER than some legitimate hits and can only be handled by the prompt; that measured limitation is itself worth writing up. Deliberately skip HyDE/query-rewriting (measured negative on well-formed queries per arXiv 2504.08231; adds a paid call per question).

*Why:* The hard context-only prompt plus a year-stale corpus produces the app's worst honest failure mode: confident refusals about the current meta. Labeled fallback plus an in-prompt vintage line converts those into useful, honestly-caveated answers for a few extra output tokens, and degrades gracefully as patch ingestion makes the corpus current.

*Inspiration:* Adaptive-RAG / DoTA-RAG routing pragmatics; arXiv 2504.08231 for the HyDE non-adoption

*Files:* `backend/app/services/rag_service.py`

### RA5. Exact-match answer cache in the existing SQLite, invalidated by index version
**Impact:** medium · **Effort:** S

Add a meta_answer_cache table to the schema in C:/Users/sergi/Valorant-ai-companion/backend/app/db.py (verified as the app's single schema home — tilt_snapshots, claude_spend, ip_usage follow the same pattern): key = sha256(lowercased, whitespace-collapsed question) + an index-version stamp; ask_meta checks it before _query and stores {answer, sources} JSON after a successful Claude call; bump the stamp in reindex() and at build-time ingest so patch updates invalidate stale answers. Explicitly skip semantic/similarity caching — false hits would serve wrong-patch info (arXiv 2607.04281 documents the failure mode) — and note in the code why Anthropic prompt caching cannot help this flow (the ~120-token system prompt is under the minimum cacheable prefix and retrieved context varies per question). Add a one-line comment noting that cache hits still consume the caller's ai_quota (the dependency runs before ask_meta) — conservative and intended.

*Why:* The four example chips are one-click questions guaranteed to repeat across visitors, and each repeat currently costs a full opus call (~1-2c and 2-8s at $5/$25 per MTok); an exact-match cache makes the most common interactions instant and free while staying trivially correct. Small, boring, defensible hobby-budget engineering.

*Inspiration:* arXiv 2607.04281 (why NOT semantic caching); Claude prompt-caching docs (why prompt cache can't apply)

*Files:* `backend/app/db.py`, `backend/app/services/rag_service.py`

### RA6. Citation UX: answer-derived sources with a parse fallback, tap-to-reveal snippets, and a metadata-derived vintage caption
**Impact:** medium · **Effort:** M

Backend: in ask_meta (rag_service.py:167-194), switch to the output_config json_schema pattern already proven in claude_service.analyze_matches_structured (claude_service.py:116-128) so Claude returns {answer, used_sources:[ids]}, then filter the sources array to chunks Claude actually used (lines 172-184 currently ship all 5, used or not) — and add a JSON-parse failure fallback that returns the answer with retrieval-derived sources so a malformed structured response degrades instead of 500ing. Extend rag_service.status() to report corpus vintage derived ONLY from explicit patch metadata (from the ingestion rec) or a hand-maintained date constant checked in beside the corpus — do NOT use knowledge-file mtime: files are COPY'd into the Docker image from a CI checkout, so mtimes are build timestamps and the caption would falsely read 'covers through <last deploy date>'. Frontend, in C:/Users/sergi/Valorant-ai-companion/frontend/src/components/MetaTab.jsx: make source chips tappable to expand the snippet inline — today it lives only in a hover title attribute (line 158), invisible to the mobile audience the app just went responsive for — and render a 'Knowledge base covers through patch X (date)' caption in the panel-sub (lines 69-73), which currently promises cited answers with zero date caveat. Keep the existing chip/panel design language; this is an elevation, not a redesign.

*Why:* Citations are this feature's whole trust story and resume differentiator, but today the chips can lie twice — wrong section labels (fixed by the chunker rec) and sources Claude never used — and the one honest disclosure that matters (the corpus is a year old) appears nowhere in the UI. Touch-accessible snippets are table stakes for the actual audience, and the mtime fix keeps the honesty feature from shipping a false freshness claim.

*Files:* `backend/app/services/rag_service.py`, `backend/app/routes/meta.py`, `frontend/src/components/MetaTab.jsx`, `frontend/src/index.css`

### RA7. Stop ensure_index() from rebuilding the corpus on the request path
**Impact:** low · **Effort:** S

Verified in C:/Users/sergi/Valorant-ai-companion/backend/app/routes/meta.py:34: every /meta/ask calls rag_service.ensure_index(), so if the baked collection is ever empty or corrupt on the live box, a random visitor's request triggers a full corpus re-embed inline — multi-second, under the module RLock, inside the proxy's 60s window, serialized against every other /meta/ask. Startup warming already exists (warm_index_async in rag_service.py:133-144), so the request path should not rebuild: replace the ensure_index() call with a cheap readiness check (collection.count() > 0, or a cached ready flag) that raises a 503 'knowledge base is warming up' — the frontend already renders a graceful offline notice for exactly this case (MetaTab.jsx unavailable panel). Keep ensure_index for startup and the admin /meta/reindex flow.

*Why:* A latent reliability trap on the single small box: the slow path punishes an arbitrary visitor and holds the lock against all concurrent askers, while the 503 path is already designed for. Small, verified, and the fix is a few lines.

*Files:* `backend/app/routes/meta.py`, `backend/app/services/rag_service.py`

### RA8. Deferred, eval-gated: in-process BM25 hybrid, FlashRank rerank, and a Haiku cost A/B
**Impact:** low · **Effort:** M

Three measured decisions to take only after the chunker fixes and gold-set eval land, in order: (1) Hybrid retrieval — the draft's Chroma-native sparse-index approach is verified broken on this stack (chromadb 1.5.9 PersistentClient fails with 'Sparse vector indexing is not enabled in local' — it is Chroma Cloud-only — and Bm25EmbeddingFunction raises ModuleNotFoundError: fastembed), and dense-only already ranks 'economy.md > Weapon prices' #1 for the Phantom-cost probe, so the motivating gap is smaller than claimed. If the eval still shows lexical misses, implement BM25 in-process instead: a ~50-line pure-Python scorer (or the tiny rank-bm25 package) over the 74 chunks, fused with dense results via RRF inside ask_meta — no Chroma schema changes, no dual-path _get_collection/reindex trap. (2) If compound-question misses persist after that (the 'comp for Ascent' class spanning team-comps.md and maps.md), add flashrank (~4MB ONNX, no torch — onnxruntime 1.27.0 verified already in the venv via chromadb) to rerank ~15 hybrid candidates down to 5-8; skip paid reranker APIs and torch-dragging embedding upgrades, and write both non-adoptions up in the README. (3) With the eval harness plus a small answer-quality rubric, run an honest cost/quality A/B of Haiku 4.5 (~5x cheaper per token) for /meta/ask — grounded extractive Q&A over ~1K tokens of context is the easiest workload to downgrade; adopt or reject on the numbers, either way a measured portfolio decision.

*Why:* Honest scoring: on a 74-chunk corpus the headroom after the chunker fixes is genuinely small, the hybrid mechanism the draft proposed does not work locally, and each of these adds latency, dependencies, or model risk — so all three stay behind the eval gate. The gating discipline, and the written non-adoptions, are themselves the portfolio story.

*Inspiration:* Anthropic Contextual Retrieval hybrid/rerank numbers; PrithivirajDamodaran/FlashRank; rank-bm25

*Files:* `backend/app/services/rag_service.py`, `backend/requirements.txt`, `backend/Dockerfile`

## Track: infra

The AWS setup is unusually solid for a solo hobby project — OIDC push-to-deploy over SSM with no stored keys, SSM SecureString secrets, a two-factor origin lockdown, layered cost/abuse controls through claude_service._create, and an integrity-checked nightly SQLite backup to versioned S3 (both stale memory claims about missing spend caps were refuted on current main). The real gaps are all about what happens when nobody is watching: zero tests on main, deploys not actually gated on CI despite lint.yml's comment claiming so, every alert originating inside the app process so a dead box or silently failing backup timer notifies no one, no restore path at all (and the instance role is deliberately write-only to the backup bucket, so a naive restore script would AccessDenied), DEPLOYMENT.md's ops table still teaching the exact torn-copy backup method backup.sh was written to replace, and the HenrikDev 30 req/min key burned 3-4x per session with zero caching. Most of the roadmap already exists as origin/security/config-and-proxy-trust, a verified clean fast-forward from main HEAD 8491da5.

### IN1. Merge origin/security/config-and-proxy-trust and arm it properly
**Impact:** high · **Effort:** S

Fast-forward main to the branch (verified: merge-base == main HEAD 8491da5, zero conflicts possible), keeping the DynamoDB budget store dormant — leave /vac/BUDGET_TABLE_NAME unset, since its DynamoStore would ImportError today (boto3 is lazily imported and absent from backend/requirements.txt; pin boto3 before ever flipping it). Then do the three activation steps the branch silently requires: (1) add /vac/ENVIRONMENT=production to SSM so HSTS and the CORS-wildcard refusal actually turn on (both gate on ENVIRONMENT, default 'development' — inert otherwise); (2) the documented two-step key rename — add /vac/HENRIK_API_KEY, deploy, then delete /vac/RIOT_API_KEY; (3) confirm the CI tests job goes green with its chromadb-stubbing requirements-dev.txt. This single merge delivers /health + /health/ready, security headers, hardened CORS, fail-closed budget counters, and the project's first ~385-line test suite.

*Why:* Highest-leverage action available: three of the track's biggest gaps (no health endpoint, no tests, credentialed-wildcard CORS) are already fixed in reviewed, written code one `git merge --ff-only` away — and every other recommendation below that references /health wants this merged first.

*Inspiration:* origin/security/config-and-proxy-trust commits b7804dc, 6009ac3, 8b7808d, 41b95b6, 3a224f2

*Files:* `backend/app/main.py`, `backend/app/health.py`, `backend/app/budget_store.py`, `backend/app/budget.py`, `backend/tests/`, `backend/requirements.txt`, `backend/requirements-dev.txt`, `.github/workflows/lint.yml`, `infra/bootstrap.sh`

### IN2. Make CI actually gate the deploy, build the frontend in CI, and smoke-test readiness
**Impact:** high · **Effort:** S

lint.yml's header says it 'gates the deploy' but deploy.yml (verified) is an independent workflow with no needs: — both fire on push to main, so a red lint (and, post-merge, a red test suite) deploys anyway. Move the ruff job, the branch's pytest job, and a new ~2-minute frontend job (npm ci && npm run build in frontend/, which has a build script and package-lock.json) into deploy.yml as jobs the deploy job declares with needs: [lint, test, frontend-build]; keep the deploy job's `if: vars.AWS_ROLE_ARN != ''` and concurrency group; keep lint.yml for pull_request only. Also fix what the smoke test measures: deploy.yml currently curls /api/ and /api/meta/status (lines 66-75), both of which return 200 even when ANTHROPIC_API_KEY or the HenrikDev key is missing from SSM — switch it to /api/health/ready post-merge, which returns 503 in exactly that state, turning the existing smoke test into a real configuration gate for one changed URL. Today a broken Vite build is discovered mid-deploy via 5 minutes of SSM polling (prod survives because compose builds before swapping, but main is left undeployable).

*Why:* The whole point of writing the first test suite is lost if a red suite still ships, and a smoke test that passes on a misconfigured deploy is theater. One workflow-file restructure plus one URL change, no new infrastructure.

*Files:* `.github/workflows/deploy.yml`, `.github/workflows/lint.yml`

### IN3. Outside-in alerting: uptime monitor on /api/health + backup dead-man switch
**Impact:** high · **Effort:** S

Two 10-minute setups that alert when the box itself is dead — the one failure mode the existing Discord alerting structurally cannot report. (1) A free external monitor (Better Stack free tier or UptimeRobot) pointed at https://rebuy.gg/api/health (post-merge; /api/ until then) — NEVER bare /health: Caddyfile's SPA fallback (`try_files {path} /index.html`, verified line 34) answers 200 with index.html while the API container is dead, so the bare path would watch the static shell, not the app; /api/* is also the CloudFront behavior with caching disabled, so no CDN cache can mask an outage. Wire it to the existing Discord webhook channel. (2) A Healthchecks.io check (free, native Discord integration) pinged by appending `curl -fsS -m 10 --retry 3 https://hc-ping.com/<uuid>` as the last line of infra/backup.sh — set -euo pipefail (verified line 17) guarantees it fires only after the S3 upload succeeded, so a silently failing nightly timer alerts within a day. Optionally add `OnFailure=vac-backup-alert.service` (a oneshot Discord-webhook curl) to the vac-backup.service unit deploy.sh writes at line 46, for immediate failure detail.

*Why:* Verified: alerts.py, the compose healthcheck, and the deploy smoke test all run inside the app or at deploy time — between deploys, rebuy.gg being down or backups being broken is discovered only by a user complaint. Biggest observability hole, $0 to close.

*Inspiration:* https://healthchecks.io/docs/monitoring_cron_jobs/

*Files:* `infra/backup.sh`, `infra/deploy.sh`, `DEPLOYMENT.md`

### IN4. TTL-cache HenrikDev responses in riot_service.py
**Impact:** high · **Effort:** S

Add a small in-process TTL cache in _henrik_get keyed on (url, frozenset(params.items())): a module-level dict of (expiry, payload) using time.monotonic(), ~120s TTL for account lookups and ~90s for match history, checked before the httpx call and pruned opportunistically — stdlib-only, matching the alerts.py dedupe-dict idiom, roughly 20-25 lines. Correct here because uvicorn runs a single process (no --workers in the Dockerfile CMD). Verified: riot_service.py has zero caching, and /claude/analyze, /mental/tilt-check, and /mental/coach each call get_match_history for the same player with effectively identical params (size=10, mode=competitive), so one user touring the tabs burns 3-4 upstream calls returning identical data — against a 30 req/min key where HenrikDev bills background Riot calls too.

*Why:* This is the binding scaling constraint (ARCHITECTURE.md's own #1 recommendation: ~5 upstream calls/session = ~6 concurrent sessions) and a reliability issue — quota exhaustion surfaces as 429s to real users. The cache multiplies effective capacity ~3-4x and cuts tab-switch latency to zero, for one small function.

*Inspiration:* ARCHITECTURE.md recommendation #1; https://docs.henrikdev.xyz/valorant/changes/v4.0.0

*Files:* `backend/app/services/riot_service.py`, `backend/tests/test_riot_cache.py (new, post-merge)`

### IN5. Write infra/restore.sh, run one restore drill, and make the ops table stop lying
**Impact:** high · **Effort:** M

infra/ has backup.sh but no restore path anywhere. Write restore.sh to: list the bucket, pull the newest companion/*.sqlite3.gz (or an argument-named key), gunzip, run PRAGMA integrity_check + a tilt_snapshots row count, stop the api container, move the current db aside AND delete stale companion.sqlite3-wal/-shm files (so SQLite cannot replay a mismatched WAL over the restored file), copy the restored file in, restart, and verify with `curl -H "X-Origin-Verify: ..." http://localhost/api/health` — the exact pattern deploy.sh:74 already uses. First decide where the download runs: bootstrap.sh:115 grants the instance role a deliberately write-only S3 policy (s3:PutObject/ListBucket/DeleteObject, no GetObject — verified), so either add s3:GetObject scoped to the companion/* prefix in bootstrap.sh (mildly weakens the write-only posture; bucket versioning still protects history) or pull with the operator's own credentials and ship the file over SSM. Run the drill once against the live box in a quiet hour, executing backup.sh immediately beforehand so 'restoring over itself' rolls the DB back minutes, not 24 hours of tilt_snapshots; record the measured RTO. Same commit, fix the ops documentation: DEPLOYMENT.md:96 still instructs `sudo docker compose cp api:/app/state/companion.sqlite3` — a plain copy of a live WAL-mode database, the exact torn-backup method backup.sh's own header warns against — replace it with `sudo /opt/vac/infra/backup.sh`, add a Restore row, a timer-status row (`systemctl list-timers vac-backup.timer`), and a rollback row ('git revert <sha> && git push' — the only rollback, since deploy.sh does git reset --hard origin/main, and it is written nowhere); fix backup.sh:4's stale 'installed as a cron job' comment (systemd timer since 334c362). Litestream stays deliberately deferred: 24h RPO plus a dead-man-monitored snapshot is a defensible stopping point for a solo maintainer — note it in DEPLOYMENT.md as the known upgrade.

*Why:* backup.sh's own comment says it: 'A backup nobody checked is a backup you find out about during the restore.' The root EBS is DeleteOnTermination=true; today recovery would be improvised under stress against an IAM policy that denies the download, following docs that teach a corrupting backup method.

*Inspiration:* https://litestream.io/how-it-works/ (evaluated and deliberately deferred)

*Files:* `infra/restore.sh`, `infra/bootstrap.sh`, `infra/backup.sh`, `DEPLOYMENT.md`

### IN6. Watchdogs for the three ways the box dies: instance death, disk-fill, hung container
**Impact:** medium · **Effort:** S

(1) One CloudWatch alarm on StatusCheckFailed -> SNS email — agentless, always-free tier; add the put-metric-alarm block to infra/bootstrap.sh so re-provisioning recreates it (no alarm of any kind exists there today). Redundant with rec 3's external monitor on box-death, but at $0 it survives a broken Discord webhook and distinguishes instance failure from CloudFront/app failure. (2) Disk: skip the CloudWatch agent — a ~5-line df check that curls the existing Discord webhook when root-volume usage exceeds 85%. (3) Hung container: docker-compose.yml defines an api healthcheck but `restart: unless-stopped` only acts on process exit, never on health status (verified lines 23-30) — a hung-but-alive uvicorn stays dead until a human notices. Close both (2) and (3) with one small on-box watchdog script + 5-minute systemd timer, written by deploy.sh alongside the backup units it already writes: check df, check `docker compose ps --filter health=unhealthy`, restart api and curl the Discord webhook when either trips. No autoheal sidecar, no Prometheus — two alarms and one timer cover the actual threat model for $0.

*Why:* docker-compose.yml's own comment calls disk-fill 'the most likely way this app dies unattended' and deploy.sh fights it with prune + a 2 GB builder-cache cap, yet nothing measures it; instance death and hung-uvicorn likewise alert nobody today. This closes the detection-to-recovery loop in the project's established idiom.

*Files:* `infra/bootstrap.sh`, `infra/deploy.sh`, `docker-compose.yml`

### IN7. AWS-side and Anthropic-side money guardrails
**Impact:** medium · **Effort:** S

Three one-time, free, zero-maintenance actions beneath the (verified strong) app-level breaker: (1) an AWS Budget at ~1.5x normal monthly spend with email alerts at 50/80/100% — codified as an aws budgets create-budget block in infra/bootstrap.sh; (2) enable Cost Anomaly Detection with the default service monitor (console, once); (3) set the monthly spend cap in the Anthropic console — budget.py's docstring literally asks for this ('the one no bug of ours can defeat') and it still is not set. Document all three in DEPLOYMENT.md's ops table.

*Why:* Every existing dollar-guardrail lives in app code on the box; a bug, a compromised instance, or plain AWS drift (bootstrap.sh itself allocates an EIP that bills when unattached) bypasses all of it. These are the only controls outside the blast radius, and the codebase has been asking for one of them since the breaker was written.

*Inspiration:* budget.py's own docstring

*Files:* `infra/bootstrap.sh`, `DEPLOYMENT.md`

### IN8. Small-hardening batch: SQLite pragma, container caps, grouped Dependabot, auto security patches, legacy cleanup
**Impact:** low · **Effort:** S

One housekeeping commit, individually verified: (1) db.py get_conn() sets busy_timeout per-connection but never synchronous — add conn.execute("PRAGMA synchronous=NORMAL") next to the busy_timeout line (per-connection, outside the _initialized block; the setting does not persist in the db file); corruption-safe in WAL, drops an fsync per commit. (2) docker-compose.yml: security_opt: ["no-new-privileges:true"] on both services and cap_drop: [ALL] on api (non-root uid 1000; leave web — Caddy binds :80 as container root). (3) .github/dependabot.yml with weekly pip + npm + github-actions updates AND a groups: block producing one grouped minor/patch PR per ecosystem — requirements.txt pins ~24 packages including transitive deps, so ungrouped weekly PRs would be a steady noise stream that violates the zero-burden promise. (4) Automatic security patches: the AL2023 box runs unattended for months and nothing ever updates kernel/Docker/openssl — add `dnf install -y dnf-automatic` + `systemctl enable --now dnf-automatic.timer` (security-only default) to infra/user-data.sh (verified: no update mechanism exists in infra/ today). (5) Delete render.yaml and frontend/vercel.json — confirmed dead pre-AWS configs still referencing the deprecated RIOT_API_KEY name — leaving a one-line history note in DEPLOYMENT.md. Optional belt-and-braces, honestly framed: claude_service.record_spend's usage-is-None path is practically unreachable (message.usage is always present on a successful SDK response) — a 3-line conservative estimate from prompt length + max_tokens is fine to add, but it is defense-in-depth, not a live under-counting bug. Still deliberately skipped as disproportionate: Trivy scanning, digest-pinned base images, distroless rewrites.

*Why:* Each item is under 10 lines, none deserves its own slot, and together they close the remaining hygiene gaps — including an internet-facing box a student forgets during exams never receiving a security patch — without adding operational burden.

*Inspiration:* https://oneuptime.com/blog/post/2026-02-02-sqlite-production-setup/view; https://docs.aws.amazon.com/linux/al2023/ug/deterministic-upgrades-usage.html

*Files:* `backend/app/db.py`, `docker-compose.yml`, `.github/dependabot.yml`, `infra/user-data.sh`, `render.yaml (delete)`, `frontend/vercel.json (delete)`, `backend/app/services/claude_service.py`, `DEPLOYMENT.md`

## Integrated roadmap

```json
{
  "roadmap": "Valorant AI Companion — integrated frontend/RAG/infra sequencing (2026-09-04)",
  "waves": [
    {
      "wave": 1,
      "theme": "Keystone merge + zero-dependency protection (everything else rebases on this)",
      "items": [
        {"track": "infra", "title": "Merge origin/security/config-and-proxy-trust + arm it (ENVIRONMENT=production, HENRIK_API_KEY rename, CI tests green)", "effort": "S"},
        {"track": "infra", "title": "Make CI actually gate the deploy (needs: lint/test/frontend-build) + /api/health/ready smoke test", "effort": "S"},
        {"track": "infra", "title": "Outside-in alerting: uptime monitor on /api/health + backup dead-man switch", "effort": "S"},
        {"track": "infra", "title": "TTL-cache HenrikDev responses in riot_service.py", "effort": "S"},
        {"track": "frontend", "title": "App-level React ErrorBoundary", "effort": "S"},
        {"track": "frontend", "title": "Privacy-policy footer link (closes Aug-21 compliance item)", "effort": "S"}
      ]
    },
    {
      "wave": 2,
      "theme": "Measurement harnesses + verified-defect fixes + recovery drill",
      "items": [
        {"track": "rag", "title": "Gold-set retrieval eval with negative probes + cached CI model (rides on wave-1 merge)", "effort": "S"},
        {"track": "rag", "title": "Chunker fixes, contextual headers, de-index disclaimer boilerplate, n_results 5->8 (measured against the eval)", "effort": "S"},
        {"track": "rag", "title": "Stop ensure_index() rebuilding on the request path (503 readiness check)", "effort": "S"},
        {"track": "frontend", "title": "Frontend CI floor: ESLint + first Vitest specs, wired into the restructured workflow", "effort": "M"},
        {"track": "frontend", "title": "Self-host resized WebP splashes and insignia icons (~20MB -> ~1.5MB)", "effort": "M"},
        {"track": "frontend", "title": "Shareable URLs + OG tags", "effort": "S"},
        {"track": "infra", "title": "infra/restore.sh + one live restore drill + fix DEPLOYMENT.md ops table", "effort": "M"},
        {"track": "infra", "title": "Watchdogs: instance death, disk-fill, hung container", "effort": "S"},
        {"track": "infra", "title": "AWS Budget + Cost Anomaly Detection + Anthropic console spend cap", "effort": "S"}
      ]
    },
    {
      "wave": 3,
      "theme": "Freshness, trust UX, and polish (consumes wave-2 eval + metadata plumbing)",
      "items": [
        {"track": "rag", "title": "Patch-notes ingestion from VALORANT Wiki (commit-and-deploy, per-file patch/date metadata)", "effort": "M"},
        {"track": "rag", "title": "Two-tier answering + gold-set-tuned distance floor + corpus-vintage line in prompt", "effort": "S"},
        {"track": "rag", "title": "Exact-match answer cache in SQLite, index-version invalidated", "effort": "S"},
        {"track": "rag", "title": "Citation UX: used-sources via json_schema, tap-to-reveal snippets, metadata-derived vintage caption", "effort": "M"},
        {"track": "frontend", "title": "Finish the tabs: selector bug, full ARIA, chat live region, contrast", "effort": "M"},
        {"track": "frontend", "title": "Network discipline: timeouts, aborts, Cancel, stopwatch", "effort": "M"},
        {"track": "frontend", "title": "Backdrop hygiene, finite pulses, lazy ScrambledText footer", "effort": "S"},
        {"track": "infra", "title": "Small-hardening batch: SQLite pragma, container caps, grouped Dependabot, dnf-automatic, legacy-config cleanup", "effort": "S"}
      ]
    },
    {
      "wave": 4,
      "theme": "Eval-gated deferred work — proceed only on measured misses",
      "items": [
        {"track": "rag", "title": "In-process BM25 hybrid -> FlashRank rerank -> Haiku cost/quality A/B, in that order, each gated on the wave-2 eval", "effort": "M"}
      ]
    }
  ],
  "cross_track_notes": [
    "Keystone dependency: the security branch merge (infra, wave 1) is a hard precondition for the RAG gold-set eval (it supplies backend/tests/, conftest.py, pytest deps, CI test runs) and for frontend CI (same lint.yml). Merge it first; every later CI-touching PR rebases on it — the frontend plan already anticipates this coordination.",
    "CI-file convergence, land in this order: (1) branch merge adds the pytest step, (2) infra restructure moves lint/test/frontend-build into deploy.yml as needs: of deploy and keeps lint.yml for PRs, (3) frontend ESLint/Vitest job and the RAG eval job are then added into that restructured layout — NOT into standalone lint.yml as the frontend draft assumed. The RAG eval job must ship with the actions/cache of the MiniLM model or it becomes the slowest CI step.",
    "Duplicate work item: frontend/vercel.json deletion appears in both the frontend-CI rec and the infra small-hardening batch — do it once (wave 2, frontend CI PR) and drop it from the wave-3 hardening batch.",
    "Genuine conflict to resolve at implementation: the frontend network-discipline rec sets a 90s client timeout for Claude routes, but the infra/RAG plans note the reverse proxy holds a 60s window — the 90s abort would never fire before a proxy 504. Align the client timeout to ~60s or raise the proxy timeout in the same PR (implementation detail, not a plan change).",
    "File contention, sequence-only: MetaTab.jsx is touched by frontend network-discipline (wave 3) and RAG citation UX (wave 3) — land sequentially, no design conflict. App.jsx accumulates shareable-URLs (wave 2), tabs/ARIA and network-discipline (wave 3) — small sequential PRs, not one mega-change.",
    "RAG internal ordering: eval (wave 2) must precede distance-floor tuning (wave 3) and gates all wave-4 work — a measured legit hit at 1.345 sits 0.06 from the drafted 1.4 floor, so no floor ships untuned. Chunker fixes bump the index version, so land the answer cache with or after them to avoid immediate cache invalidation churn.",
    "Vintage disclosures (system-prompt line, wave 3; UI caption, wave 3) consume the per-file patch/date metadata from patch-notes ingestion — land ingestion first within wave 3, or start from the plans' sanctioned hand-maintained constant and upgrade when metadata exists.",
    "Deploy coupling: every RAG corpus/chunker change ships via the build-time re-embed on normal deploy — which is why CI-gating the deploy is wave 1, before the RAG track starts deploying frequently.",
    "Plan-stated frontend ordering preserved: self-host assets (wave 2) before backdrop hygiene (wave 3) so paint/bandwidth wins are measured against local assets.",
    "Wave-1 internal ordering: point the uptime monitor at /api/ only if armed before the merge lands; switch to /api/health immediately after — same for the deploy smoke test moving to /api/health/ready."
  ]
}
```
