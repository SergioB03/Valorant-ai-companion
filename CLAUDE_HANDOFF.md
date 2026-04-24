# 🤖 Claude Code Handoff — Valorant AI Companion

> Living handoff doc. Updated at natural stopping points so any fresh Claude session (any machine) can pick up seamlessly. **Point at files; do not embed source** — embedded code rots fast.

**Last refresh:** 2026-04-24 — both backend pillars complete, hardened, BYOK decision made.

---

## 📍 Project at a glance

**Valorant AI Companion** — two-pillar AI app for the Valorant community:

1. **Performance Analyst** — pulls match history via Henrik's unofficial Valorant API, sends to Claude for personalized gameplay breakdowns
2. **Mental Coach** — deterministic tilt-signal detector + Claude-generated mental reset advice

**Developer:** Sergio Banuelos — CS student at Western Governors University. This is a **portfolio piece targeting FAANG/Microsoft engineering roles**. Prioritize clean code, clear architecture, and good commit hygiene — employers will read this repo.

**Environment:** Windows 11, VS Code, **Git Bash** is the primary terminal. Prefer forward slashes in paths. The `py` launcher is used (not `python`). No virtualenv currently — packages installed globally to Python 3.13.

**Repo:** https://github.com/sergioB03/Valorant-ai-companion

---

## ✅ Current state (as of last refresh)

### Working API endpoints

| Method | Endpoint | Returns | Notes |
|---|---|---|---|
| GET | `/` | JSON | Health check |
| POST | `/claude/ask` | JSON | Generic prompt → Claude. Rate-limited 3/min |
| GET | `/claude/analyze/{name}/{tag}` | JSON | Match analysis (legacy/Swagger-friendly) |
| GET | `/claude/analyze/stream/{name}/{tag}` | SSE | Streaming match analysis for frontend |
| GET | `/riot/account/{name}/{tag}` | JSON | Account lookup via Henrik |
| GET | `/riot/matches/{name}/{tag}?size=N` | JSON | Match history summaries |
| GET | `/mental/coach/{name}/{tag}` | JSON | Tilt signals + coaching (legacy/Swagger) |
| GET | `/mental/coach/stream/{name}/{tag}` | SSE | Streaming tilt signals + coaching |

### Streaming event contract

Streaming endpoints emit Server-Sent Events with these event names:

- `progress` — `{"stage": "fetching_matches" | "detecting_patterns" | "analyzing" | "coaching", ...}`
- `signals` — *(mental coach only)* structured tilt-signal breakdown before the text starts
- `token` — `{"text": "..."}` — Claude's streaming output, one chunk at a time
- `done` — final summary with `match_count`
- `error` — `{"message": "..."}` — any failure mid-stream (the HTTP status was already 200 by then)

Frontend consumes with `EventSource` or an SSE-capable `fetch` reader.

### What's hardened

- Per-IP rate limiting via slowapi — `3/min` on `/claude/ask`, `10/min` on analyze + coach, `20/min` on riot
- `httpx.Timeout(10.0, connect=5.0)` on all Henrik calls so upstream hangs can't stall workers
- `urllib.parse.quote` on all path parameters before concatenating into external URLs
- Exception messages sanitized — real errors go to `logger.exception`, client sees generic 4xx/5xx
- `CLAUDE_MODEL` env var (default `claude-sonnet-4-6`) and `ALLOWED_ORIGINS` env var (default `http://localhost:5173`) so prod deploys don't need code changes

---

## 🧠 Architecture — how to reason about it

**Layered separation:**

- **routes/** — HTTP concerns only. Validation, auth decorators, streaming response wrapping, error status codes. Should be thin.
- **services/** — business logic. Pure Python where possible. No FastAPI imports.
- **limiter.py** — single shared slowapi `Limiter` instance; imported by both `main.py` (registration) and route files (decorators).

**Pattern: sync vs streaming.** Every Claude-powered feature has two forms:
- A sync `service_function(...)` that returns a string — used by JSON endpoints
- An `async stream_service_function(...)` that yields strings — used by SSE endpoints

Both share one prompt-building helper so there's one source of truth for prompt text. See [backend/app/services/claude_service.py](backend/app/services/claude_service.py) — `_build_analysis_prompt` feeds both `analyze_matches` and `stream_analysis`. Same pattern in [backend/app/services/mental_service.py](backend/app/services/mental_service.py).

**Pattern: algorithmic signals before LLM.** Mental Coach computes tilt signals in pure Python *first* (`detect_tilt_signals` — loss streak, KDA trend, HS% trend, most-lost map/agent, 0-100 tilt_score), then passes those structured signals into Claude's prompt. This is intentional: cheap + deterministic + testable algorithm feeds expensive + fuzzy LLM. Do this for future analytical features too.

**Generic Claude streaming primitive.** `claude_service.stream_claude(prompt)` is the reusable async generator that wraps Anthropic's `async_client.messages.stream`. Features shouldn't call the Anthropic SDK directly — build a prompt and pass it to `ask_claude` or `stream_claude`.

---

## 🗂 File map

```
Valorant-ai-companion/
├── README.md                                # project description + roadmap checklist
├── CLAUDE_HANDOFF.md                        # this file
├── riot.txt                                 # Riot verification (needs deployed domain)
├── .gitignore                               # covers .env, venv, .claude/, chroma_db
├── backend/
│   ├── .env                                 # ANTHROPIC_API_KEY, RIOT_API_KEY (Henrik), optional CLAUDE_MODEL, ALLOWED_ORIGINS — NEVER committed
│   ├── .env.example                         # template with placeholders
│   ├── requirements.txt                     # pinned deps incl. slowapi==0.1.9
│   └── app/
│       ├── main.py                          # FastAPI app, CORS, limiter registration, router includes
│       ├── limiter.py                       # shared slowapi Limiter
│       ├── routes/
│       │   ├── claude.py                    # /claude/ask, /claude/analyze, /claude/analyze/stream
│       │   ├── mental.py                    # /mental/coach, /mental/coach/stream
│       │   └── riot.py                      # /riot/account, /riot/matches
│       └── services/
│           ├── claude_service.py            # Anthropic clients (sync + async), generic stream_claude, analyze helpers
│           ├── mental_service.py            # detect_tilt_signals + coach prompt + coach/stream_coach
│           └── riot_service.py              # Henrik API wrappers + summarize_matches
└── frontend/                                # not yet scaffolded (React + Vite planned)
```

---

## 🔑 Environment variables (backend/.env)

Required:
- `ANTHROPIC_API_KEY` — starts with `sk-ant-`. For local dev only; production will be BYOK (see next section).
- `RIOT_API_KEY` — currently holds a **Henrik** key (format `HDEV-...`), obtained from the HenrikDev Discord. The var name is misleading; rename candidates exist but deferred.

Optional (documented in `.env.example`):
- `CLAUDE_MODEL` — defaults to `claude-sonnet-4-6`
- `ALLOWED_ORIGINS` — comma-separated CORS origins, defaults to `http://localhost:5173`

---

## 🚀 How to run locally (Git Bash)

```bash
# From project root, not backend/
py -m uvicorn app.main:app --reload --port 8000 --app-dir backend
```

Then `http://localhost:8000/docs` for Swagger. Stream endpoints work in Swagger only partially — use `curl -N` for a real streaming view:

```bash
curl -N http://localhost:8000/claude/analyze/stream/<name>/<tag>
curl -N http://localhost:8000/mental/coach/stream/<name>/<tag>
```

**Gotcha:** uvicorn `--reload` watches `.py` files only — **changes to `.env` require a full restart** to take effect.

---

## 🔜 What's next (in order)

### 1. BYOK (Bring-Your-Own-Key) wiring — **do this before frontend**

**Decision:** Users supply their own Anthropic API key. Server never pays for user-triggered Claude calls. Non-negotiable in production.

**Why:** This is a passion project, not a business. Anthropic is the only meaningful cost center, and BYOK eliminates it entirely. Freemium/hosted-tier options stay on the shelf until the project gets traction.

**Implementation plan (rough):**
- Add `X-Anthropic-Key` header support on all `/claude/*` and `/mental/*` endpoints
- Instantiate `anthropic.Anthropic(api_key=...)` / `anthropic.AsyncAnthropic(api_key=...)` **per request** using the header value — do not store or log the key
- Gate the existing server-owned fallback behind `ALLOW_SERVER_KEY_FALLBACK=true` env var so local dev stays frictionless but production can't accidentally enable it
- Refactor `ask_claude` / `stream_claude` to accept an optional client or key parameter, with the module-level client as the dev fallback
- Update streaming endpoints to bubble up a clear SSE `error` event if the user's key is missing or invalid

**Frontend implications (for when you build the React UI):** user pastes key into a settings panel → stored in `localStorage` only → attached as header on every API call. Explicit "we never send this anywhere but Anthropic" copy in the UI.

### 2. React + Vite frontend

Scaffolded in `frontend/` (doesn't exist yet). Pages: Home, Dashboard (enter Riot ID → see analysis), Mental Coach (tilt signals + coaching), Settings (for BYOK key). Tailwind CSS planned. Use `EventSource` to consume the SSE streams.

**Entertaining loading UX:** when the user hits analyze/coach, show rotating Valorant-flavored copy ("Checking your headspace...", "Asking Claude what Brimstone would say...", etc.) keyed to the `progress` event `stage` field. Dumb client-side timer is fine for v1; upgrade to strict SSE-driven later if it feels flat.

### 3. Deployment

- Frontend → **Vercel** (free tier fine for passion project)
- Backend → **Render** free tier (sleeps after 15 min, cold start ~30s — acceptable). Add all env vars to the dashboard.
- Once backend is deployed at a real domain, update Riot's production key application with the verified `riot.txt` URL and wait for approval.

### 4. RAG pipeline (ChromaDB)

Meta/patch-note questions via `/claude/meta` with RAG over patch notes + pro match data. `pip install chromadb sentence-transformers`. Deferred — not critical for the core pitch.

### 5. User session memory

Longer-term: tilt profile that improves over sessions. Needs a DB (SQLite for simple, Postgres for prod). Deferred.

### 6. Demo video

Last step before calling the project "portfolio-ready."

---

## ⚠️ Things NOT to do

- **Don't** hardcode the Claude model name in new code. Use `CLAUDE_MODEL` env var via `claude_service`.
- **Don't** call the Anthropic SDK directly from routes or mental_service. Go through `ask_claude` / `stream_claude`.
- **Don't** interpolate user input directly into external URLs. Wrap with `urllib.parse.quote(value, safe='')`.
- **Don't** return `str(e)` in error responses. `logger.exception(...)` server-side, return a generic `detail` to the client.
- **Don't** add a server-owned Anthropic key path that works in production. BYOK only.
- **Don't** ask the user to paste API keys in chat — keys live in `.env` or (future) localStorage only.
- **Don't** commit `.claude/` (already gitignored) or `.env` (already gitignored).
- **Don't** treat this handoff as source-of-truth for code. Read the actual files. This doc describes intent and architecture, code describes reality.

---

## 📌 Small project quirks worth knowing

- Riot production API key is **pending approval**. Henrik's unofficial API (`api.henrikdev.xyz`) is the active data source. Official Riot code lives commented-out in `riot_service.py` for the day approval lands.
- The env var is named `RIOT_API_KEY` but currently holds the **Henrik** key. Deliberate not-yet-renamed compromise.
- Henrik's dev key expires/needs-rotating when abused — regenerate from their Discord if auth breaks.
- `.claude/` directory is VS Code Claude Code local settings — gitignored, machine-local, never pushed.
