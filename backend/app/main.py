import os
from dotenv import load_dotenv

load_dotenv()

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.alerts import notify_error
from app.limiter import limiter
from app.routes import analytics, claude, riot, mental, meta
from app.services.rag_service import warm_index_async

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    warm_index_async()  # build the RAG index in the background instead of on the first request
    yield

# ROOT_PATH (e.g. "/api") is the prefix a reverse proxy strips before forwarding to us;
# FastAPI needs it so /docs can find /openapi.json. Leave unset for local dev.
app = FastAPI(
    title="Valorant AI Companion",
    version="1.0.0",
    lifespan=lifespan,
    root_path=os.getenv("ROOT_PATH", ""),
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Last line of defense: anything a route didn't map gets logged, alerted, and sanitized.
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    notify_error(f"{request.method} {request.url.path}", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(claude.router)
app.include_router(riot.router)
app.include_router(mental.router)
app.include_router(meta.router)
app.include_router(analytics.router)

@app.get("/")
def root():
    return {"message": "Valorant AI Companion API is running 🚀"}
