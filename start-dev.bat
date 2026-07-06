@echo off
REM Valorant AI Companion - local dev launcher (Windows)
REM Backend runs on port 8001 here; the manual flow in README.md uses uvicorn's default 8000.
REM First run bootstraps everything: venv + pip install, npm install, .env from .env.example.
REM Opens backend + frontend in their own windows, then opens the app in your browser.

cd /d %~dp0

REM --- backend virtualenv ---
if not exist backend\venv\Scripts\python.exe (
    echo [setup] Creating backend virtualenv...
    python -m venv backend\venv
)
if not exist backend\venv\Scripts\python.exe (
    echo [error] Could not create the virtualenv. Install Python 3.12+ and make sure "python" is on PATH.
    pause
    exit /b 1
)

REM --- backend dependencies ---
backend\venv\Scripts\python.exe -c "import uvicorn" 2>nul || (
    echo [setup] Installing backend dependencies...
    backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
)

REM --- env file ---
if not exist backend\.env (
    copy backend\.env.example backend\.env >nul
    echo [setup] Created backend\.env from .env.example.
    echo [setup] Add your ANTHROPIC_API_KEY and RIOT_API_KEY to backend\.env or the app won't return data.
)

REM --- frontend dependencies ---
if not exist frontend\node_modules (
    echo [setup] Installing frontend dependencies...
    cd frontend
    call npm install
    cd ..
)

start "vac-backend" cmd /k "cd /d %~dp0backend && venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001"
start "vac-frontend" cmd /k "cd /d %~dp0frontend && set VITE_API_URL=http://localhost:8001&& npm run dev"

timeout /t 5 /nobreak >nul
start http://localhost:5173/
