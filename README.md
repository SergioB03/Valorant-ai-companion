🧠 Valorant AI Companion
Because mechanics only get you so far — your mental gets you the rest of the way.

The Problem
There are a hundred aim trainers, stat trackers, and coach sites for Valorant.
But almost nothing that says: "Hey — before you queue again, how's your headspace?"
I've played Valorant long enough to know that tilt kills more games than bad aim. Whether you're a casual player just trying to have fun, grinding ranked, or competing at a high level — mental is the most undercoached skill in the game. This project exists to change that.

What It Does
Valorant AI Companion is a full-stack AI-powered app with two core pillars:
📊 Performance Analyst

Connects to the Riot Games API to pull your real match history
Analyzes your stats: KDA, headshot %, win rate by agent, map performance, and more
Uses Claude AI to generate personalized, plain-English breakdowns of your gameplay
Answers meta questions like "Is Jett still good this patch?" using RAG (Retrieval-Augmented Generation) on patch notes and pro data

🧠 Mental Coach

Detects tilt patterns from your match history — loss streaks, performance drops, time-of-day trends
Identifies your emotional triggers (specific maps, agents, game modes)
Delivers personalized mental reset routines and focus strategies
Builds a mental profile over time so advice gets smarter the more you use it
Designed for casual, competitive, and pro players alike


Tech Stack:
LayerTechnologyFrontendReact + ViteBackendPython + FastAPIAIAnthropic Claude APIGame DataRiot Games APIVector DB (RAG)ChromaDBDeploymentVercel (frontend) + Render (backend)Version ControlGitHub

Why I Built This-
I love Valorant. And after spending time in the community — watching players grind, tilt, and quit — I noticed something. Coaches everywhere talk about crosshair placement and util usage. Almost nobody talks about the mental side.
Casual players stop enjoying the game. Ranked players force matches after loss streaks. Even pros have talked openly about mental blocks costing them tournaments.
This project is my attempt to bridge that gap — combining my passion for the game with real AI engineering skills. The goal is to build something the community actually needs, not just another stats dashboard.

Features Roadmap:

 Project scaffolding and architecture
 Riot API integration — match history, stats
 FastAPI backend with Claude API integration
 Match performance analysis endpoint
 Tilt pattern detection algorithm
 Mental Coach AI responses
 React frontend dashboard
 RAG pipeline — patch notes + meta data
 User session memory (mental profile over time)
 Deployment to Vercel + Render
 Demo video


Getting Started
Prerequisites:

Python 3.10+
Node.js 18+
Riot Games Developer Account → developer.riotgames.com
Anthropic API Key → console.anthropic.com

Backend Setup:
bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

Create a .env file in /backend:
ANTHROPIC_API_KEY
RIOT_API_KEY
Run the server:
bashuvicorn app.main:app --reload
Frontend Setup
bashcd frontend
npm install
npm run dev

Project Structure:
valorant-ai-companion/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── routes/
│   │   │   ├── riot.py         # Riot API endpoints
│   │   │   ├── claude.py       # Claude AI endpoints
│   │   │   └── mental.py       # Mental coach endpoints
│   │   └── services/
│   │       ├── riot_service.py
│   │       ├── claude_service.py
│   │       └── mental_service.py
│   ├── .env
│   └── requirements.txt
└── frontend/
    └── src/

Screenshots:
Coming soon as the project develops.

Contributing:
This is a personal passion project for now, but feedback and ideas are always welcome. Open an issue or reach out directly.

Author:
Sergio Banuelos
Computer Science Student @ Western Governors University
Building at the intersection of AI and the things I love.

Built with: Claude API · Riot Games API · FastAPI · React

Development Tools: VS Code · GitHub · Claude AI (pair programming — all architecture decisions, system design, and core logic authored by me.)

Project is not endored by Riot.

Legal:
Valorant AI Companion isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties.