# Architecture & RAG design

Two systems documented here, each **as it is today** and **as it should be**,
with the reasoning in between. Every number is measured against the real corpus,
the real index, and the live deployment — nothing is estimated unless it says so.

The optimisation target is deliberately unusual: **make this work well on a
cheap model.** The app currently runs `claude-opus-4-8`, which costs about
5× what `claude-haiku-4-5` does. A strong model can paper over a mediocre
retrieval pipeline using what it already knows about Valorant. A small one
can't. So "optimise for Haiku" really means "stop relying on the model to
rescue us."

---

## Part 1 — The RAG pipeline

`POST /api/meta/ask` answers Valorant meta questions from a hand-written
knowledge base.

### Current design

```
INGEST  (at image build time, so containers start query-ready)
┌────────────────────────────────────────────────────────────────┐
│ backend/data/knowledge/*.md                                    │
│   9 files · 38,974 chars · hand-written, changes rarely        │
└──────────────────────────────┬─────────────────────────────────┘
                               v
CHUNK   rag_service.chunk_markdown()
┌────────────────────────────────────────────────────────────────┐
│ split on "## " headings                                        │
│ sections > MAX_CHUNK_CHARS (1200) split again on newlines      │
│ merge neighbours while either < MIN_CHUNK_CHARS (200)          │
│                                                                │
│ -> 74 chunks · min 201 · max 1190 · mean 524 chars             │
│ metadata: {source: "maps.md", section: "Sunset"}               │
└──────────────────────────────┬─────────────────────────────────┘
                               v
EMBED   all-MiniLM-L6-v2 (ONNX, 384-dim) — Chroma's default
┌────────────────────────────────────────────────────────────────┐
│ embeds the chunk BODY ONLY                                     │
│ source + section live in metadata, never in the vector         │
└──────────────────────────────┬─────────────────────────────────┘
                               v
STORE   ChromaDB (in-process, persistent dir baked into the image)

              ──────── request time ────────

question ─> RETRIEVE   collection.query(n_results=5)
            ┌──────────────────────────────────────────┐
            │ pure dense similarity                    │
            │ no keyword search, no rerank,            │
            │ no metadata filter, NO score threshold   │
            │ -> top 5 always returned, whatever       │
            │    the scores look like                  │
            └────────────────┬─────────────────────────┘
                             v
            ASSEMBLE
            ┌──────────────────────────────────────────┐
            │ "[{source} — {section}]\n{doc}"          │
            │ joined by "\n\n---\n\n" + "Question: {q}"│
            │ system: answer ONLY from context, cite   │
            └────────────────┬─────────────────────────┘
                             v
            ANSWER   claude-opus-4-8, thinking: adaptive
            MEASURED: 1,143 in / 357 out · $0.0146 · ~6.8 s
```

### What's actually wrong with it

Measured, not guessed. I built a small eval set of real questions and ran it
against the live index.

**Retrieval quality: recall@3 = 4/6 (67%).** Two of six realistic questions
fail to surface the right document at all:

| Question | Wanted | Got (top 3) |
|---|---|---|
| "Who is Tejo and what does he do?" | `agents-meta.md` | patch notes ×3 ❌ |
| "How should I play Sunset?" | `maps.md` | patch notes, team-comps, roles ❌ |
| "What changed in patch 10.04?" | `patch-notes-recent.md` | ✅ |
| "What does a duelist do?" | `roles-guide.md` | ✅ |
| "When should I force buy?" | `economy.md` | ✅ |
| "How does ranked RR work?" | `ranked-system.md` | ✅ |

Both failures are **proper nouns** — an agent name and a map name. That is the
known weak spot of a small 384-dimensional embedding model, and this corpus is
made almost entirely of proper nouns. "Sunset" retrieved a patch-notes chunk
that happens to begin `Patch 10.04 — March 2025 (su…` — a near-miss on a
substring, not on meaning.

**Three concrete defects behind that number:**

1. **The vector doesn't know what it's about.** Only the chunk body is embedded;
   `source` and `section` sit in metadata. A chunk reading
   `- Identity: Los Angeles-themed…` contains no token saying *Sunset*, *map*,
   or *Valorant*. **12 of 74 chunks** don't even begin with their own heading.

2. **A labelling bug in the chunker.** `chunk_markdown` initialises
   `heading = source`, so each file's preamble is labelled with the *filename*.
   **9 of 74 chunks** carry a section label like `roles-guide.md` instead of a
   real heading — and that string is what the model is told to cite and what
   the API returns in `sources[]`.

3. **Two chunks are cut mid-sentence**, both in `agents-meta.md` — the only file
   with sections over the 1200-char limit. One ends `…Missile-based initiator:
   Guided` with the rest of the sentence in the next chunk. Tejo's name and his
   abilities end up in different chunks, which is exactly why that query misses.

**No out-of-scope path.** "What's the weather today?" retrieves five Valorant
chunks and pays for a full model call. But the measurement also shows the fix:
its best distance is **1.722**, while in-scope questions score **0.74–1.30**.
The populations separate cleanly, so a threshold works here — no classifier
needed.

**And the blocker in front of everything:** `thinking={"type": "adaptive"}` is
hardcoded at both Claude call sites. `claude-haiku-4-5` **rejects it with HTTP
400** (verified by direct API call). So "just switch to a cheaper model" is not
a config change today — it's an outage.

### Optimized design

```
CHUNK   *** MAX_CHUNK_CHARS 1200 -> 2000 ***
┌────────────────────────────────────────────────────────────────┐
│ only agents-meta.md exceeds the old limit, so raising it       │
│ removes BOTH mid-sentence splits and keeps every agent's       │
│ name with their abilities.  cost: 0 lines of new logic         │
│                                                                │
│ *** carry the heading through the merge step ***               │
│ -> filename-labelled chunks: 9 -> 0                            │
└──────────────────────────────┬─────────────────────────────────┘
                               v
EMBED   *** prepend the heading to the embedded text ***
┌────────────────────────────────────────────────────────────────┐
│ embed  "Valorant · maps · Sunset\n\n{body}"                    │
│ instead of just "{body}"                                       │
│                                                                │
│ this is the single highest-leverage change: it puts the        │
│ proper nouns the query contains INTO the vector being          │
│ searched. Both current failures are proper-noun failures.      │
└──────────────────────────────┬─────────────────────────────────┘
                               v
RETRIEVE  *** n_results 5 -> 4, plus a distance threshold ***
┌────────────────────────────────────────────────────────────────┐
│ drop chunks beyond ~1.5 distance                               │
│   -> out-of-scope questions retrieve NOTHING and the endpoint  │
│      answers "not in my knowledge base" without a model call   │
│      (measured separation: in-scope 0.74–1.30, off-topic 1.72) │
│                                                                │
│ 4 instead of 5 because a small model is more easily distracted │
│ by a marginal chunk than helped by it                          │
└──────────────────────────────┬─────────────────────────────────┘
                               v
ASSEMBLE  *** question first AND last · drop the "---" rules ***
┌────────────────────────────────────────────────────────────────┐
│ small models attend better when the task brackets the context  │
│ separators cost tokens and carry no meaning                    │
└──────────────────────────────┬─────────────────────────────────┘
                               v
ANSWER   *** per-model thinking config ***
┌────────────────────────────────────────────────────────────────┐
│ a capability map, not a hardcoded parameter, so CLAUDE_MODEL   │
│ becomes a real switch:                                         │
│   opus/sonnet -> thinking={"type": "adaptive"}                 │
│   haiku       -> omit thinking entirely                        │
└────────────────────────────────────────────────────────────────┘
```

### Why it's better — and what it costs

| Change | Gain | Honest tradeoff |
|---|---|---|
| Heading in embedded text | Targets both measured failures directly | Re-index required; heading tokens slightly dilute very long chunks |
| `MAX_CHUNK_CHARS` → 2000 | Removes both mid-sentence splits | Larger chunks = more tokens per retrieved hit; only safe because this corpus is small |
| Fix the merge-step label | 9 mislabelled chunks → 0; citations become truthful | None — it's a bug fix |
| Distance threshold | Off-topic questions cost **$0** instead of a full call | A badly-worded real question may get refused; the threshold needs tuning against real traffic |
| `n_results` 5 → 4 | ~20% fewer context tokens, less distraction | If retrieval is wrong, there's one less chance of luck |
| Per-model thinking | **Unblocks Haiku entirely** — 5× cheaper | Haiku genuinely reasons less well; keep the strong model for paid/complex paths |

**Estimated combined effect** (marked as an estimate — the token counts follow
from the changes, the quality claim needs real traffic to confirm): roughly
**1,143 → ~800 input tokens**, and on Haiku about **$0.0146 → ~$0.002** per
question, a ~85% reduction — *with better retrieval, not worse*.

### What we deliberately did NOT do

- **A reranker.** Standard advice for large corpora. With 74 chunks the
  retriever already sees nearly everything; a cross-encoder adds latency and a
  second model for a problem that better embedding text solves.
- **Hybrid BM25 + dense search.** Genuinely tempting given the proper-noun
  failures — but putting the heading into the embedded text addresses the same
  failures without a second index to build and keep in sync. Revisit if the
  measurement says the cheap fix wasn't enough.
- **Prompt caching.** The system prompt is short and the retrieved context
  changes every question, so there is no stable prefix long enough to cache.
- **A vector database server.** Chroma in-process with the index baked into the
  image needs no network hop, no second container, and no cold start.
- **Semantic/recursive chunking.** The corpus is markdown written by one person
  with clean `##` headings. The structure is already the semantics.

> The pattern worth taking away: at this scale, **fixing what you embed beat
> every technique for changing how you search.**

---

## Part 2 — System design

### Current

```
                    ┌──────────────┐
   browser ────────>│  CloudFront  │  TLS, CDN, caches static assets
                    └──────┬───────┘  adds X-Origin-Verify secret header
                           │ HTTP (origin-facing ranges only)
                           v
              ┌────────────────────────┐
              │  EC2 t3.small          │  Elastic IP · no SSH port open
              │  ┌──────────────────┐  │
              │  │ Caddy  (web)     │  │  serves the SPA
              │  │  /api/* ─────────┼──┼─> strips prefix, proxies
              │  └────────┬─────────┘  │
              │           v            │
              │  ┌──────────────────┐  │
              │  │ FastAPI (api)    │  │  ← 1 uvicorn worker
              │  │  ChromaDB (proc) │  │
              │  │  SQLite (volume) │  │  ← no backups
              │  └────────┬─────────┘  │
              └───────────┼────────────┘
                          ├──> Anthropic API   (daily $ ceiling, per-IP quota)
                          └──> HenrikDev API   (30 req/min · NO CACHE)
```

**The binding constraint is not the server.** It's the two upstreams:

- **HenrikDev allows 30 requests/min** and nothing caches responses. One user
  session makes **~5 upstream calls** (dashboard account + matches, analyze,
  tilt-check, coach). That's a ceiling of roughly **6 concurrent sessions/min**
  before a third party starts refusing you — long before the CPU notices.
- **One uvicorn worker.** Claude calls take 5–10 s and run in a threadpool, so
  they don't block the loop, but throughput is still bounded.
- **Growth shows up as an Anthropic bill, not CPU.** At the measured 4.7¢ per
  session, 100 sessions/day is ~$141/month of model spend against a ~$21/month
  server. **Watch spend, not CPU.**

### Optimized

```
                    ┌──────────────┐
   browser ────────>│  CloudFront  │  (unchanged — already doing its job)
                    └──────┬───────┘
                           v
              ┌────────────────────────┐
              │  EC2 t3.small          │
              │  ┌──────────────────┐  │
              │  │ Caddy  (web)     │  │
              │  └────────┬─────────┘  │
              │           v            │
              │  ┌──────────────────┐  │
              │  │ FastAPI (api)    │  │
              │  │                  │  │
              │  │ *** upstream     │  │  NEW: TTL cache in SQLite, keyed on
              │  │     cache ***    │  │  (region, name, tag, size, mode)
              │  │                  │  │  ~5 min TTL
              │  │  ChromaDB        │  │
              │  │  SQLite ─────────┼──┼─> *** nightly backup ***
              │  └────────┬─────────┘  │
              └───────────┼────────────┘
                          ├──> Anthropic  (+ per-model thinking config)
                          └──> HenrikDev  (~5 calls/session -> ~2)
```

**Ordered by value per unit of effort:**

1. **Cache upstream responses** (~20 lines). One session's dashboard, analyze,
   tilt-check and coach all fetch overlapping match data. Caching on
   `(region, name, tag, size, mode)` — **`mode` matters**, since different
   routes request `competitive` vs unfiltered — cuts ~5 calls to ~2 and roughly
   **doubles the concurrent-user ceiling for free.**
2. **Back up the SQLite file.** `tilt_snapshots` is the only irreplaceable data
   here and it sits on a volume with `DeleteOnTermination=true`.
3. **Per-model thinking config** — unblocks the 5× cheaper model.

**What NOT to change, and why:**

- **Keep one instance.** Managed-container alternatives priced out at 2–3× the
  current bill, mostly because they force a load balancer (~$16/mo) to do TLS
  and routing that CloudFront already does for free.
- **Keep SQLite.** A single-writer embedded database is genuinely correct at
  this scale, and the app's state is small.
- **Keep one uvicorn worker for now.** Adding workers looks like an easy win but
  the rate limiter holds counters **in process memory** and the spend counters
  assume a single writer. More workers means those controls silently weaken —
  they'd have to move to shared storage *first*.
- **Keep Chroma in-process.** No network hop, no extra container.

> The general lesson: **find the constraint before optimising.** Here it's a
> third-party API's 30 req/min and a per-token model bill — not CPU, not RAM,
> and not the thing a scaling tutorial would tell you to fix.
