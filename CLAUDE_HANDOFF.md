# 🤖 Claude Code Handoff — Valorant AI Companion
> Instructions for Claude Code (VS Code) to continue building this project from current progress.

---

## 📍 Project Overview
**Valorant AI Companion** — A full-stack AI-powered app with two pillars:
1. **Performance Analyst** — pulls real Valorant match data via Henrik's API and uses Claude AI to generate personalized gameplay breakdowns
2. **Mental Coach** — detects tilt patterns, emotional triggers, and delivers personalized mental strategies

**Developer:** Sergio Banuelos
**Goal:** Portfolio piece targeting FAANG/Microsoft roles
**Repo:** https://github.com/sergioB03/Valorant-ai-companion

---

## ✅ What's Already Built & Working

### Backend (Python + FastAPI)
- ✅ FastAPI server running with uvicorn
- ✅ CORS middleware configured for React dev server (localhost:5173)
- ✅ Claude API connected and responding via Anthropic SDK
- ✅ Henrik's Unofficial Valorant API connected (replaces Riot official API temporarily)
- ✅ Account lookup by Riot ID working
- ✅ Match history endpoint working and returning clean summarized data
- ✅ Match summarizer built (extracts map, agent, KDA, HS%, win/loss from raw data)
- ✅ Claude match analysis endpoint working — feeds real match data to Claude for personalized coaching
- ✅ All routes registered in main.py
- ✅ .env file set up with both API keys (never committed to GitHub)
- ✅ Virtual environment set up in backend/venv
- ✅ Riot production API key application submitted (pending approval)
- ✅ Henrik API key active and in use

### Project Files
- ✅ README.md — full project description, stack, roadmap, Riot legal disclaimer
- ✅ LICENSE — MIT
- ✅ .gitignore — covers .env, venv, node_modules, __pycache__, ChromaDB
- ✅ riot.txt — Riot verification file in repo root

---

## 📁 Current Project Structure
```
Valorant-ai-companion/
├── .gitignore
├── LICENSE
├── README.md
├── riot.txt                          # Riot API verification file
├── backend/
│   ├── .env                          # API keys (NOT in GitHub)
│   ├── requirements.txt
│   ├── venv/                         # Python virtual environment
│   └── app/
│       ├── __init__.py
│       ├── main.py                   # FastAPI app, CORS, router registration
│       ├── routes/
│       │   ├── __init__.py
│       │   ├── claude.py             # /claude/ask and /claude/analyze endpoints
│       │   ├── riot.py               # /riot/account and /riot/matches endpoints
│       │   └── mental.py             # (empty - next to build)
│       ├── services/
│       │   ├── __init__.py
│       │   ├── claude_service.py     # ask_claude() and analyze_matches()
│       │   ├── riot_service.py       # Henrik API integration + summarize_matches()
│       │   └── mental_service.py     # (empty - next to build)
│       └── models/
│           └── __init__.py
└── frontend/                         # (empty - React app to be scaffolded)
```

---

## 📄 Current File Contents

### backend/app/main.py
```python
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import claude, riot

app = FastAPI(title="Valorant AI Companion", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(claude.router)
app.include_router(riot.router)

@app.get("/")
def root():
    return {"message": "Valorant AI Companion API is running 🚀"}
```

### backend/app/services/claude_service.py
```python
import os
import anthropic
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def ask_claude(prompt: str) -> str:
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    return message.content[0].text

def analyze_matches(match_summaries: list) -> str:
    matches_text = "\n".join([
        f"- {m['map']} | {m['agent']} | {m['kills']}/{m['deaths']}/{m['assists']} | HS%: {m['headshot_percent']} | {'Win' if m['won'] else 'Loss'}"
        for m in match_summaries
    ])
    
    prompt = f"""You are an expert Valorant performance analyst and mental coach.
    
Here are the player's recent matches:
{matches_text}

Give a personalized analysis covering:
1. Performance patterns you notice
2. Strengths to build on
3. Areas to improve
4. One mental/tilt warning sign if any
5. One actionable tip for their next game

Keep it concise, direct and encouraging."""

    return ask_claude(prompt)
```

### backend/app/services/riot_service.py
```python
import os
import httpx
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# ---- OFFICIAL RIOT API (pending production approval) ----
# RIOT_API_KEY = os.getenv("RIOT_API_KEY")
#
# async def get_account_by_riot_id(game_name: str, tag_line: str, region: str = "americas"):
#     url = f"https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
#     headers = {"X-Riot-Token": RIOT_API_KEY}
#     async with httpx.AsyncClient() as client:
#         response = await client.get(url, headers=headers)
#         response.raise_for_status()
#         return response.json()
#
# async def get_match_history(puuid: str, region: str = "americas"):
#     url = f"https://{region}.api.riotgames.com/val/match/v1/matchlists/by-puuid/{puuid}"
#     headers = {"X-Riot-Token": RIOT_API_KEY}
#     async with httpx.AsyncClient() as client:
#         response = await client.get(url, headers=headers)
#         response.raise_for_status()
#         return response.json()
# ---------------------------------------------------------

# ---- HENRIK UNOFFICIAL API (active) ----
HENRIK_API_KEY = os.getenv("RIOT_API_KEY")
HENRIK_BASE_URL = "https://api.henrikdev.xyz/valorant"

async def get_account_by_riot_id(game_name: str, tag_line: str):
    url = f"{HENRIK_BASE_URL}/v1/account/{game_name}/{tag_line}"
    headers = {"Authorization": HENRIK_API_KEY}
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

async def get_match_history(game_name: str, tag_line: str, region: str = "na"):
    url = f"{HENRIK_BASE_URL}/v3/matches/{region}/{game_name}/{tag_line}"
    headers = {"Authorization": HENRIK_API_KEY}
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        raw = response.json()
        return summarize_matches(raw)

def summarize_matches(raw_matches: dict) -> list:
    summaries = []
    matches = raw_matches.get("data", [])
    
    for match in matches:
        info = match.get("metadata", {})
        players = match.get("players", {}).get("all_players", [])
        my_player = next((p for p in players if p.get("puuid") == match.get("metadata", {}).get("puuid")), players[0] if players else {})
        stats = my_player.get("stats", {})
        
        summary = {
            "match_id": info.get("matchid"),
            "map": info.get("map"),
            "mode": info.get("mode"),
            "agent": my_player.get("character"),
            "kills": stats.get("kills"),
            "deaths": stats.get("deaths"),
            "assists": stats.get("assists"),
            "headshot_percent": stats.get("headshots"),
            "score": stats.get("score"),
            "won": my_player.get("team") == match.get("teams", {}).get("winning_team"),
        }
        summaries.append(summary)
    
    return summaries
# -----------------------------------------
```

### backend/app/routes/claude.py
```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.claude_service import ask_claude, analyze_matches
from app.services.riot_service import get_match_history

router = APIRouter(prefix="/claude", tags=["claude"])

class PromptRequest(BaseModel):
    prompt: str

@router.post("/ask")
def ask(request: PromptRequest):
    response = ask_claude(request.prompt)
    return {"response": response}

@router.get("/analyze/{game_name}/{tag_line}")
async def analyze(game_name: str, tag_line: str, region: str = "na"):
    try:
        matches = await get_match_history(game_name, tag_line, region)
        analysis = analyze_matches(matches)
        return {"analysis": analysis}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
```

### backend/app/routes/riot.py
```python
from fastapi import APIRouter, HTTPException
from app.services.riot_service import get_account_by_riot_id, get_match_history

router = APIRouter(prefix="/riot", tags=["riot"])

@router.get("/account/{game_name}/{tag_line}")
async def get_account(game_name: str, tag_line: str):
    try:
        account = await get_account_by_riot_id(game_name, tag_line)
        return account
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/matches/{game_name}/{tag_line}")
async def get_matches(game_name: str, tag_line: str, region: str = "na"):
    try:
        matches = await get_match_history(game_name, tag_line, region)
        return matches
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
```

---

## 🔑 Environment Variables
File location: `backend/.env`
```
ANTHROPIC_API_KEY=sk-ant-...
RIOT_API_KEY=...  # Henrik API key currently active
```

---

## 🚀 How to Start the Server
```bash
cd backend
source venv/Scripts/activate   # Windows Git Bash
uvicorn app.main:app --reload
```
Then open: http://127.0.0.1:8000/docs

---

## 📋 Working API Endpoints
| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| GET | / | Health check | ✅ |
| POST | /claude/ask | Send any prompt to Claude | ✅ |
| GET | /claude/analyze/{game_name}/{tag_line} | Pull matches + Claude analysis | ✅ |
| GET | /riot/account/{game_name}/{tag_line} | Get account info by Riot ID | ✅ |
| GET | /riot/matches/{game_name}/{tag_line} | Get summarized match history | ✅ |

---

## 🔜 What to Build Next (in order)

### 1. Mental Coach Endpoint (mental.py + mental_service.py)
Build `/mental/coach/{game_name}/{tag_line}` that:
- Pulls match history
- Analyzes loss streaks, performance drops, tilt patterns
- Returns personalized mental reset routine
- Stores session data for profile building over time

### 2. React Frontend (Vite + React)
Scaffold with:
```bash
cd frontend
npm create vite@latest . -- --template react
npm install axios
```
Pages to build:
- Home/landing page
- Dashboard — enter Riot ID, see match analysis
- Mental Coach — tilt detection + mental tips
- Use Tailwind CSS for styling

### 3. RAG Pipeline (ChromaDB)
- Scrape/store Valorant patch notes in ChromaDB vector database
- Add `/claude/meta` endpoint that answers meta questions using RAG
- Install: `pip install chromadb sentence-transformers`

### 4. Deployment
- Frontend → Vercel
- Backend → Render
- Add environment variables to both platforms

---

## 📌 Important Notes for Claude Code
- Developer is on **Windows** using **Git Bash** — use forward slashes in paths
- Always use `source venv/Scripts/activate` (not `source venv/bin/activate`) on Windows
- The `.env` file is in `backend/` not the project root
- Henrik API is temporary — official Riot API code is commented out in `riot_service.py` for when production key is approved
- Model to use for Claude API calls: `claude-sonnet-4-20250514`
- Keep commits descriptive using conventional commits format: `feat:`, `fix:`, `chore:`
- Developer is comfortable with APIs but learning — explain decisions clearly
