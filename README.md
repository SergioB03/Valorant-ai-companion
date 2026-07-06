# 🧠 Valorant AI Companion

> Because mechanics only get you so far — your mental gets you the rest of the way.

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
- Builds a mental profile over time — every tilt check and coach conversation is saved, so advice gets smarter the more you use it
- Designed for casual, competitive, and pro players alike

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React + Vite |
| Backend | Python + FastAPI |
| AI | Anthropic Claude API |
| Game Data | HenrikDev API (Riot API migration pending) |
| Vector DB (RAG) | ChromaDB |
| Profile Storage | SQLite |
| Deployment | Vercel (frontend) + Render (backend) |
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
- [ ] Demo video
- [ ] Migrate to production Riot API key

## API Endpoints

Interactive docs live at `/docs` when the backend is running.

| Method | Endpoint | What it does |
|---|---|---|
| `GET` | `/riot/account/{name}/{tag}` | Account lookup — level, region, player card |
| `GET` | `/riot/matches/{name}/{tag}?region=na&size=10` | Recent match summaries, newest first (map, agent, K/D/A, HS%, win/loss) — `size` defaults to 3 |
| `POST` | `/claude/ask` | Free-form question straight to Claude — body `{"prompt": "..."}` |
| `GET` | `/claude/analyze/{name}/{tag}?region=na&size=10` | Claude's plain-English breakdown of your recent matches, returned as plain text — optional `size` (default 10, max 10) |
| `GET` | `/mental/tilt-check/{name}/{tag}?region=na&size=10` | Tilt report — score 0–100, level, signals, triggers, coach message |
| `POST` | `/mental/coach` | Chat with the Mental Coach — body `{"game_name", "tag_line", "region", "message"}`; replies with your current tilt context in mind |
| `GET` | `/mental/profile/{name}/{tag}` | Your mental profile — tilt snapshot history, coach sessions, and trend |
| `POST` | `/meta/ask` | Meta Q&A via RAG — body `{"question": "..."}`; answers with cited sources |
| `GET` | `/meta/status` | RAG index status (ready, documents, chunks) |
| `POST` | `/meta/reindex` | Rebuild the knowledge index from `backend/data/knowledge/` |

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- HenrikDev API key (used for match data while the production Riot key is pending — keys are issued through [HenrikDev's docs](https://docs.henrikdev.xyz) / Discord; [developer.riotgames.com](https://developer.riotgames.com) is only relevant for the future official-API migration)
- Anthropic API key → [console.anthropic.com](https://console.anthropic.com)

### Backend Setup

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
```

Run the server:

```bash
uvicorn app.main:app --reload
```

The API is now at `http://localhost:8000` (docs at `http://localhost:8000/docs`).

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The dashboard is now at `http://localhost:5173`. It talks to `http://localhost:8000` by default — set `VITE_API_URL` in a `frontend/.env` file if your backend lives elsewhere.

### Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full walkthrough: Render Blueprint (`render.yaml`) for the backend, Vercel for the frontend, and wiring `CORS_ORIGINS` between them.

## Project Structure

```
valorant-ai-companion/
├── render.yaml                 # Render Blueprint (backend deploy)
├── DEPLOYMENT.md               # Deploy walkthrough (Render + Vercel)
├── LICENSE
├── riot.txt                    # Riot site verification
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI app, CORS, router wiring
│   │   ├── db.py               # SQLite storage for the mental profile
│   │   ├── errors.py           # Upstream-error → HTTP error mapping
│   │   ├── models/             # Shared pydantic models
│   │   ├── routes/
│   │   │   ├── riot.py         # Account + match history endpoints
│   │   │   ├── claude.py       # Claude Q&A + match analysis endpoints
│   │   │   ├── mental.py       # Tilt check, coach chat, profile endpoints
│   │   │   └── meta.py         # RAG meta Q&A endpoints
│   │   └── services/
│   │       ├── riot_service.py     # HenrikDev API client + match summarizer
│   │       ├── claude_service.py   # Claude API wrapper
│   │       ├── mental_service.py   # Tilt detection + coach prompts
│   │       └── rag_service.py      # ChromaDB indexing + retrieval
│   ├── data/
│   │   ├── knowledge/          # Markdown corpus for RAG (patches, meta, maps...)
│   │   ├── chroma_db/          # Vector index (generated, gitignored)
│   │   └── companion.sqlite3   # Mental profile DB (generated, gitignored)
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
