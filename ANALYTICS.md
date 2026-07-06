# Analytics Design

Lightweight, privacy-first product analytics for the Valorant AI Companion. First-party only:
events flow from the React frontend to our own FastAPI backend and land in the same SQLite
database the app already uses. No third-party trackers, no cookies, no PII.

## Goals

- Answer "is anyone using this, and which features?" with a single admin endpoint.
- Measure the core funnel: search a player → run an analysis → tilt check → talk to the coach.
- Track perceived performance (client-side latency percentiles for the Claude-backed features).
- Track error rates by endpoint so regressions surface without log spelunking.
- Stay deployable on the current free-tier stack (Render + SQLite) with zero new infrastructure.

## Non-goals

- User identification, cross-device tracking, or marketing attribution.
- Real-time dashboards or alerting — a JSON summary endpoint is enough at this stage.
- Guaranteed exactly-once delivery. Losing a stray event batch is acceptable; billing-grade
  accuracy is not a requirement for product analytics.

## Event schema

One row per event in `analytics_events`:

| column       | type    | notes                                              |
|--------------|---------|----------------------------------------------------|
| `id`         | INTEGER | primary key                                        |
| `visitor_id` | TEXT    | anonymous UUID, generated client-side (localStorage) |
| `session_id` | TEXT    | anonymous UUID per browser session (sessionStorage) |
| `name`       | TEXT    | snake_case event name, validated `^[a-z][a-z0-9_]{0,63}$` |
| `path`       | TEXT    | client route, ≤128 chars                           |
| `props_json` | TEXT    | event properties, serialized ≤1KB (422 above that) |
| `client_ts`  | INTEGER | client clock, ms epoch — untrusted, for debugging  |
| `created_at` | TEXT    | server receive time — the source of truth for aggregates |

Client and server timestamps are stored separately on purpose: client clocks skew and users
batch events, so all aggregation uses `created_at`.

Indexes: `(name, created_at)` for the per-event and daily aggregates, `(visitor_id)` for the
COUNT DISTINCT funnel queries.

## Event vocabulary

| event                | props                                     | fired when                      |
|----------------------|-------------------------------------------|---------------------------------|
| `session_start`      | `referrer_host`                           | once per browser session        |
| `page_view`          | `tab`                                     | app mount                       |
| `tab_change`         | `tab`                                     | user switches tabs              |
| `player_search`      | `region`, `found` (bool)                  | riot account lookup resolves    |
| `analyze_run`        | `match_count`, `latency_ms`, `ok`         | match analysis completes/fails  |
| `tilt_check`         | `tilt_level`, `tilt_score`, `latency_ms`, `ok` | tilt check completes/fails |
| `coach_message_sent` | `latency_ms`, `ok`                        | coach chat round-trip           |
| `meta_question`      | `latency_ms`, `ok`, `unavailable`         | meta Q&A round-trip             |
| `api_error`          | `endpoint` (path template), `status`      | any API call throws             |

The vocabulary is closed: the frontend emits exactly these names, and anything else is still
accepted by the regex but simply ignored by the funnel/latency aggregates.

## Privacy stance

- **Anonymous IDs only.** `visitor_id` is a random UUID in localStorage; `session_id` in
  sessionStorage. Neither is derived from anything about the user, and clearing storage resets them.
- **No PII.** Riot names/tags never appear in props — `player_search` records only the region and
  whether the lookup resolved. `api_error` records the path *template*, never path parameters.
- **No cookies**, no fingerprinting, no third-party requests.
- **Do Not Track respected client-side**: `navigator.doNotTrack === "1"` turns the entire client
  into a no-op, as does building with `VITE_ANALYTICS=off`.
- IP addresses are used transiently for rate limiting but are never written to the events table.

## Delivery semantics (client)

The client queues events and flushes every 10 seconds or when 10 events accumulate, via
`fetch(…, { keepalive: true })`. On `visibilitychange → hidden` it flushes through
`navigator.sendBeacon` so tab closes don't drop the tail of a session. Failed flushes are
re-queued once, with the queue capped at 50 (oldest dropped beyond that).

This is **at-least-once** delivery: a batch whose response is lost may be retried and land twice,
and **ordering is not guaranteed** across batches. That's acceptable because events are
idempotent facts — aggregates count occurrences and unique visitors, and a rare duplicate batch
moves no decision we'd make from this data. No dedupe machinery is therefore needed.

## Ingestion & rate limiting

`POST /analytics/events` is unauthenticated (it has to be — it's called by anonymous browsers),
so it is deliberately hard to abuse:

- Strict pydantic validation: 8–64 char IDs, 1–25 events per batch, snake_case names ≤64 chars,
  paths ≤128 chars, props ≤1KB serialized. Oversized or malformed input → 422 before any write.
- 120 requests/minute per IP via slowapi (in-memory, per-process — fine for one Render instance).
- Inserts are a single `executemany` transaction; a batch is all-or-nothing.

Claude-backed endpoints get tighter per-IP limits (`/claude/ask` 5/min, `/claude/analyze` and
`/mental/tilt-check` 10/min, `/mental/coach` and `/meta/ask` 15/min) because each request costs
real money upstream. A determined attacker with many IPs can still exceed these; the next rung of
defense would be an edge/WAF layer, not application code.

## Reading the data

`GET /analytics/summary` returns totals, a 14-day daily series, all-time counts per event, the
search→analyze→tilt→coach funnel (unique visitors per step), p50/p95 latency for the three
Claude features, and error counts by endpoint+status. It requires the `X-Admin-Token` header to
match the `ADMIN_TOKEN` env var (compared with `secrets.compare_digest`); when the var is unset
the endpoint always returns 403, so the deploy is private-by-default.

## Why SQLite now, and the scaling path

SQLite is already this app's datastore, adds zero operational surface, and handles this write
volume (single-digit events/second at best) trivially with WAL mode. When it stops fitting:

1. **Postgres** — same schema, same queries, real concurrent writes; the natural move when the
   backend outgrows one Render instance (which also fixes per-process rate-limit state).
2. **Queue + columnar store** (Redis/SQS worker → ClickHouse or BigQuery) — when event volume
   makes in-request writes or full-scan aggregates noticeable. At that point add **sampling** for
   high-frequency events and nightly **rollup tables** so the summary reads from pre-aggregates.

## What I'd measure next

- **Retention cohorts**: week-over-week returning `visitor_id`s, cohorted by first-seen week —
  the real "is this useful?" signal that raw event counts can't answer.
- **Error budgets**: error rate per endpoint against a target (e.g. 99% of `analyze_run` ok),
  tracked weekly so a flaky upstream shows up as a trend rather than an anecdote.
- Funnel drop-off *within* a session (search → analyze conversion time) and p99 latency once
  volume makes tail percentiles statistically meaningful.

## Tradeoffs, explicitly

- **In-request writes vs a queue**: the insert happens on the request thread (FastAPI thread
  pool). Simplest possible design, adds a few ms; a queue only earns its complexity when write
  volume or datastore latency grows.
- **Python percentiles vs SQL window functions**: latencies are fetched and ranked in Python.
  O(n) transfer of one column is fine at this scale and keeps the SQL portable; at real volume
  this becomes `PERCENTILE_CONT`/`quantile()` in the database, or pre-aggregated histograms.
- **Per-IP, in-memory rate limiting**: resets on deploy, shared across users behind one NAT, and
  per-process. Correct tradeoff for one free-tier instance; Redis-backed storage is the upgrade.
- **At-least-once ingestion without dedupe**: occasional duplicates are cheaper than an idempotency
  key scheme the analysis doesn't need.
