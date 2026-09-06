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
from app.routes import analytics, claude, health, riot, mental, meta
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

# A wildcard origin is refused outside local development. Starlette does not send
# a literal "*" when credentials are enabled -- it echoes the caller's own origin
# back -- so "*" is not the harmless catch-all it looks like: it makes every site
# on the internet a permitted origin. Failing at import beats discovering it later.
if "*" in origins and os.getenv("ENVIRONMENT", "development") != "development":
    raise RuntimeError("CORS_ORIGINS must not contain '*' outside development")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    # No cookies or session auth anywhere in the app -- the admin routes take a
    # header (X-Admin-Token) and the frontend never sets credentials: "include".
    # Credentialed CORS therefore buys nothing while making a misconfigured
    # origin list considerably more dangerous.
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token"],
    # The quota interface the frontend reads (see app/deps.py ai_quota):
    # without these, cross-origin JS can't see the headers at all.
    expose_headers=["X-Quota-Exhausted", "X-Quota-Limit", "Retry-After"],
    max_age=3600,
)

# Endpoints that spend AI money. Their responses are per-caller (and now carry
# per-caller quota headers), so neither CloudFront nor the browser may ever
# cache them — a cached copy would hand one visitor another's answer/quota.
AI_SPEND_PATH_PREFIXES = (
    "/claude/analyze",
    "/mental/tilt-check",
    "/mental/coach",
    "/meta/ask",
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Headers a JSON API should always send.

    nosniff stops a browser second-guessing our content type; DENY and the
    frame-ancestors directive keep responses out of an attacker's iframe; the
    referrer policy keeps Riot IDs in our URLs from leaking to third parties via
    the Referer header. HSTS is set only in production, where TLS terminates at
    CloudFront -- sending it from a local HTTP dev server would pin developers
    to https://localhost.
    """
    response = await call_next(request)
    if request.url.path.startswith(AI_SPEND_PATH_PREFIXES):
        # Set unconditionally (not setdefault): no-store must win on every
        # response from these paths, success and error alike.
        response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
    )
    if os.getenv("ENVIRONMENT", "development") == "production":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response

app.include_router(health.router)
app.include_router(claude.router)
app.include_router(riot.router)
app.include_router(mental.router)
app.include_router(meta.router)
app.include_router(analytics.router)

@app.get("/")
def root():
    return {"message": "Valorant AI Companion API is running 🚀"}
