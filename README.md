# 🧠 Valorant AI Companion

[![Lint](https://github.com/SergioB03/Valorant-ai-companion/actions/workflows/lint.yml/badge.svg)](https://github.com/SergioB03/Valorant-ai-companion/actions/workflows/lint.yml)
[![Deploy to AWS](https://github.com/SergioB03/Valorant-ai-companion/actions/workflows/deploy.yml/badge.svg)](https://github.com/SergioB03/Valorant-ai-companion/actions/workflows/deploy.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)

> Because mechanics only get you so far — your mental gets you the rest of the way.

**Live:** [rebuy.gg](https://rebuy.gg)

**Two write-ups, both worth more than the code:**
- [SECURITY.md](./SECURITY.md) — the vulnerabilities this project shipped with, how each was found, and what fixed them
- [ARCHITECTURE.md](./ARCHITECTURE.md) — the RAG pipeline and system design, measured, analysed, and redesigned to run well on a *cheap* model (before/after schemas + tradeoffs)

## The Problem

There are a hundred aim trainers, stat trackers, and coach sites for Valorant.

But almost nothing that says: **"Hey — before you queue again, how's your headspace?"**

I've played Valorant long enough to know that tilt kills more games than bad aim. Whether you're a casual player just trying to have fun, grinding ranked, or competing at a high level — mental is the most undercoached skill in the game. This project exists to change that.

## What It Does

Valorant AI Companion is a full-stack AI-powered app with two core pillars:

### 📊 Performance Analyst

- Pulls your real match history (via the HenrikDev API while my production Riot API key is pending — a commented-out official Riot API starting point lives in `riot_service.py`, but it uses a different, puuid-based flow and will need adaptation when the production key arrives)
- Analyzes your stats: KDA, headshot %, win rate, agent and map performance, and more
- Uses Claude AI to generate personalized, plain-English breakdowns of your gameplay
- Answers meta questions like "Is Jett still good this patch?" using RAG (Retrieval-Augmented Generation) over a curated knowledge base of patch summaries, agent meta, maps, economy, and ranked info

### 🧠 Mental Coach

- Detects tilt patterns from your match history — loss streaks, KDA and headshot % drops, low win rates
- Identifies your emotional triggers (specific maps and agents you keep losing on)
- Scores your tilt 0–100 and delivers a personalized coach message plus a concrete recommendation ("queue up" vs. "stop for today")
- Builds a mental profile over time — tilt scores are tracked across sessions so you can see whether your headspace is trending up or down
- **Conversations are never stored server-side.** An early version filed chat text under the *searched* player's Riot ID, where anyone could read it back; see [SECURITY.md](./SECURITY.md)
- Designed for casual, competitive, and pro players alike

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React + Vite |
| Backend | Python + FastAPI |
| AI | Anthropic Claude API |
| Game Data | HenrikDev API (Riot API migration pending) |
| Vector DB (RAG) | ChromaDB |
| Storage (profiles + analytics) | SQLite |
| Deployment | AWS — EC2 running Docker Compose behind CloudFront; push-to-deploy via GitHub Actions |
| Version Control | GitHub |

## Why I Built This

I love Valorant. And after spending time in the community — watching players grind, tilt, and quit — I noticed something. Coaches everywhere talk about crosshair placement and util usage. Almost nobody talks about the mental side.

Casual players stop enjoying the game. Ranked players force matches after loss streaks. Even pros have talked openly about mental blocks costing them tournaments.

This project is my attempt to bridge that gap — combining my passion for the game with real AI engineering skills. The goal is to build something the community actually needs, not just another stats dashboard.

## Features Roadmap

- [x] Project scaffolding and architecture
- [x] Riot API integration — match history, stats
- [x] FastAPI backend with Claude API integration
- [x] Match performance analysis endpoint
- [x] Tilt pattern detection algorithm
- [x] Mental Coach AI responses
- [x] React frontend dashboard
- [x] RAG pipeline — patch notes + meta data
- [x] User session memory (mental profile over time)
- [x] Deployment configs for Vercel + Render
- [x] AWS deployment — EC2 + CloudFront, persistent SQLite, push-to-deploy GitHub Actions
- [x] Anonymous usage analytics + per-IP rate limiting
- [x] Custom domain with managed TLS ([rebuy.gg](https://rebuy.gg))
- [x] Security hardening pass — see [SECURITY.md](./SECURITY.md)
- [x] Abuse and cost controls — daily spend ceiling, per-visitor quotas, bounded inputs
- [x] Operational alerting for silent failures (budget, upstream key, rate limits)
- [ ] Automated backups of the SQLite state
- [ ] Demo video
- [ ] Migrate to production Riot API key

## Getting Started

### Quickstart (60 seconds)

1. **Clone:**

   ```bash
   git clone https://github.com/SergioB03/Valorant-ai-companion.git
   cd Valorant-ai-companion
   ```

2. **Grab your two API keys:**
   - **HenrikDev key** (match data) — join the HenrikDev Discord (required for dashboard login; the invite is on [docs.henrikdev.xyz](https://docs.henrikdev.xyz)), then sign in with Discord at [dashboard.henrikdev.xyz](https://dashboard.henrikdev.xyz) and generate a key.
   - **Anthropic key** (Claude AI) — create one at [console.anthropic.com](https://console.anthropic.com).

3. **Create your env file** and paste both keys in:

   ```bash
   cp backend/.env.example backend/.env    # Windows: copy backend\.env.example backend\.env
   ```

4. **Run it:**
   - **Windows:** double-click (or run) `start-dev.bat`. First run bootstraps everything — creates the venv, installs Python and npm dependencies, creates `backend/.env` if you skipped step 3 — then launches the backend on port **8001**, the frontend on port **5173**, and opens the app in your browser.
   - **macOS/Linux:** two terminals:

     ```bash
     # Terminal 1 — backend (http://localhost:8000)
     cd backend
     python -m venv venv && source venv/bin/activate
     pip install -r requirements.txt
     uvicorn app.main:app --reload
     ```

     ```bash
     # Terminal 2 — frontend (http://localhost:5173)
     cd frontend
     npm install
     npm run dev
     ```

Open `http://localhost:5173`, search a Riot ID (`name` + `#tag`), and you're in.

### Prerequisites

- Python 3.12+
- Node.js 18+
- HenrikDev API key (used for match data while the production Riot key is pending — keys are issued through [HenrikDev's docs](https://docs.henrikdev.xyz) / Discord; [developer.riotgames.com](https://developer.riotgames.com) is only relevant for the future official-API migration)
- Anthropic API key → [console.anthropic.com](https://console.anthropic.com)

### Backend Setup (manual)

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in `/backend` (see `backend/.env.example`):

```env
ANTHROPIC_API_KEY=your-anthropic-api-key-here
RIOT_API_KEY=your-henrikdev-api-key-here
CLAUDE_MODEL=claude-opus-4-8
CORS_ORIGINS=http://localhost:5173
ADMIN_TOKEN=
```

| Variable | Required | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | Claude API key — powers analysis, coach, and meta Q&A |
| `RIOT_API_KEY` | yes | HenrikDev API key — match history and account data |
| `CLAUDE_MODEL` | no | Claude model id (defaults are fine) |
| `CORS_ORIGINS` | no | Comma-separated allowed frontend origins (default `http://localhost:5173`) |
| `ADMIN_TOKEN` | no | Unlocks `GET /analytics/summary` via the `X-Admin-Token` header. Leave empty to keep the summary endpoint disabled (it returns 403). |

Run the server:

```bash
uvicorn app.main:app --reload
```

The API is now at `http://localhost:8000` (docs at `http://localhost:8000/docs`).

> `start-dev.bat` runs this same server on port **8001** instead (8000 is a common conflict on Windows) and points the frontend at it automatically via `VITE_API_URL`.

### Frontend Setup (manual)

```bash
cd frontend
npm install
npm run dev
```

The dashboard is now at `http://localhost:5173`. It talks to `http://localhost:8000` by default — set `VITE_API_URL` in a `frontend/.env` file if your backend lives elsewhere (e.g. `VITE_API_URL=http://localhost:8001`).

### Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md). One script (`infra/bootstrap.sh`) stands up the AWS stack, every push to `main` deploys through GitHub Actions, and `infra/add-domain.sh` puts it on a custom domain. `docker compose up --build` runs the exact production stack locally.

## API Endpoints

Interactive docs live at `/docs` when the backend is running (`/api/docs` on the deployed site, where the API is served under `/api`).

| Method | Endpoint | What it does |
|---|---|---|
| `GET` | `/riot/account/{name}/{tag}` | Account lookup — level, region, player card |
| `GET` | `/riot/matches/{name}/{tag}?region=na&size=10` | Recent match summaries, newest first (map, agent, K/D/A, HS%, win/loss) — `size` defaults to 3 |
| `GET` | `/claude/analyze/{name}/{tag}?region=na&size=10` | Claude's structured breakdown of your recent matches — `analysis` object with `overview`, `strengths[]`, `weaknesses[]`, `tilt_warning` (string or null), and `tip` — optional `size` (default 10, max 10) |
| `GET` | `/mental/tilt-check/{name}/{tag}?region=na&size=10` | Tilt report — score 0–100, level, signals, triggers, coach message |
| `POST` | `/mental/coach` | Chat with the Mental Coach — body `{"game_name", "tag_line", "region", "message", "history"}`; replies with your current tilt context in mind. `history` is your own last few turns, sent by the browser — the server keeps no transcript |
| `GET` | `/mental/profile/{name}/{tag}` | Mental profile — tilt snapshot history, coach-session counts, and trend. Any Riot ID can be requested by anyone, so this returns aggregates only, never the text of a coach conversation (15/min) |
| `POST` | `/meta/ask` | Meta Q&A via RAG — body `{"question": "..."}`; answers with cited sources |
| `GET` | `/meta/status` | RAG index status (ready, documents, chunks) |
| `POST` | `/meta/reindex` | Rebuild the knowledge index from `backend/data/knowledge/` — admin-only (`X-Admin-Token` header, same gate as `/analytics/summary`; disabled when `ADMIN_TOKEN` is unset), 10 calls/hour |
| `POST` | `/analytics/events` | Ingests batches of anonymous usage events from the frontend (1–25 events per batch, no auth, rate-limited) — returns `204 No Content` |
| `GET` | `/analytics/summary` | Admin-only usage aggregates — totals, 14-day daily counts, per-event counts, funnel, latency percentiles, error counts. Requires an `X-Admin-Token` header matching the `ADMIN_TOKEN` env var; returns 403 if `ADMIN_TOKEN` is unset |

> **Rate limiting:** Claude-backed endpoints and analytics ingestion are rate-limited per client IP — `/claude/analyze` and `/mental/tilt-check` 10/min, `/mental/coach`, `/mental/profile` and `/meta/ask` 15/min, `/analytics/events` 120/min. Exceeding a limit returns `429 Too Many Requests`.

### Analytics & Privacy

The frontend sends a small set of anonymous usage events (tab views, searches, analysis runs, latencies, errors) so I can see what people actually use. Design details live in [ANALYTICS.md](ANALYTICS.md). The short version:

- **Anonymous** — a random UUID in `localStorage` identifies a browser, nothing else. No accounts, no cookies.
- **No PII** — Riot names/tags are never sent in events; a player search reports only the region and whether the lookup succeeded.
- **Do Not Track respected** — if your browser sets DNT, the client sends nothing.
- **Opt out at build time** — set `VITE_ANALYTICS=off` in the frontend env to turn the whole client into a no-op.
- **Reading the data** — `GET /analytics/summary` is only available when the backend has `ADMIN_TOKEN` set and the request carries the matching `X-Admin-Token` header.

## Project Structure

```
valorant-ai-companion/
├── DEPLOYMENT.md               # Deploy walkthrough (AWS: EC2 + CloudFront)
├── SECURITY.md                 # Vulnerabilities found and fixed, and the lessons
├── ARCHITECTURE.md             # RAG + system design: measured, analysed, optimized
├── THIRD-PARTY-LICENSES.md     # Vendored code that isn't Apache-2.0
├── render.yaml                 # Legacy Render Blueprint (superseded by infra/)
├── ANALYTICS.md                # Analytics design doc (events, privacy, tradeoffs)
├── start-dev.bat               # Windows one-click dev launcher (backend :8001 + frontend :5173)
├── LICENSE
├── riot.txt                    # Riot site verification
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI app, CORS, rate limiter, router wiring
│   │   ├── db.py               # SQLite storage (mental profile + analytics events)
│   │   ├── errors.py           # Upstream-error → HTTP error mapping
│   │   ├── limiter.py          # Per-IP rate limiter (slowapi)
│   │   ├── models/             # Shared pydantic models
│   │   ├── routes/
│   │   │   ├── riot.py         # Account + match history endpoints
│   │   │   ├── claude.py       # Claude Q&A + match analysis endpoints
│   │   │   ├── mental.py       # Tilt check, coach chat, profile endpoints
│   │   │   ├── meta.py         # RAG meta Q&A endpoints
│   │   │   └── analytics.py    # Anonymous event ingestion + admin summary
│   │   └── services/
│   │       ├── riot_service.py     # HenrikDev API client + match summarizer
│   │       ├── claude_service.py   # Claude API wrapper
│   │       ├── mental_service.py   # Tilt detection + coach prompts
│   │       └── rag_service.py      # ChromaDB indexing + retrieval
│   ├── data/
│   │   ├── knowledge/          # Markdown corpus for RAG (patches, meta, maps...)
│   │   ├── chroma_db/          # Vector index (generated, gitignored)
│   │   └── companion.sqlite3   # SQLite DB — mental profiles + analytics (generated, gitignored)
│   ├── .env.example
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── vite.config.js
    ├── vercel.json             # SPA rewrites for Vercel
    ├── package.json
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── api.js              # Fetch wrappers for the backend endpoints
        ├── analytics.js        # Anonymous, DNT-respecting usage-event client
        ├── utils.js            # Shared formatting helpers (dates, etc.)
        ├── index.css
        └── components/
```

## Screenshots

Coming soon as the project develops.

## Contributing

This is a personal passion project for now, but feedback and ideas are always welcome. Open an issue or reach out directly.

## Author

**Sergio Banuelos**
Computer Science Student @ Western Governors University
Building at the intersection of AI and the things I love.

Built with: Claude API · HenrikDev API · FastAPI · React

Development Tools: VS Code · GitHub · Claude AI (pair programming — all architecture decisions, system design, and core logic authored by me.)

Project is not endorsed by Riot.

## Legal

Valorant AI Companion isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties.
