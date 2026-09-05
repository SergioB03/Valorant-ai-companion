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
