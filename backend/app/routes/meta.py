import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.deps import ai_quota
from app.errors import upstream_to_http
from app.limiter import limiter
from app.services import rag_service

router = APIRouter(prefix="/meta", tags=["meta"])

UNAVAILABLE_DETAIL = (
    "Meta Q&A is unavailable: chromadb is not installed on the server. "
    "Install it with 'pip install chromadb' and restart the backend."
)

class AskRequest(BaseModel):
    # Capped because every question is billed to us by the token. Without a
    # ceiling, one request could carry megabytes of text straight into a paid
    # model call. 2000 characters is far more than a real meta question needs.
    question: str = Field(min_length=1, max_length=2000)

@router.post("/ask", dependencies=[Depends(ai_quota)])
@limiter.limit("15/minute")
async def ask(request: Request, body: AskRequest):
    if not rag_service.is_available():
        raise HTTPException(status_code=503, detail=UNAVAILABLE_DETAIL)
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")
    # Readiness check only — NEVER ensure_index() here: if the baked collection
    # were empty or corrupt, ensure_index would re-embed the whole corpus inline
    # on a random visitor's request (multi-second, under the module lock, inside
    # the proxy's 60s window, serialized against every other asker). Startup
    # warming (warm_index_async) and the admin /meta/reindex own index builds;
    # the request path answers 503 + Retry-After, which the frontend already
    # renders as a graceful "warming up" notice.
    if not await run_in_threadpool(rag_service.is_ready):
        raise HTTPException(
            status_code=503,
            detail="The knowledge base is still warming up — try again in a moment.",
            headers={"Retry-After": "15"},
        )
    try:
        return await run_in_threadpool(rag_service.ask_meta, question)
    except HTTPException:
        raise
    except Exception as e:
        raise upstream_to_http(e, "meta.ask")

@router.get("/status")
async def get_status():
    try:
        result = await run_in_threadpool(rag_service.status)
    except HTTPException:
        raise
    except Exception as e:
        raise upstream_to_http(e, "meta.status")
    return {"available": rag_service.is_available(), **result}

@router.post("/reindex")
@limiter.limit("10/hour")   # counts rejected attempts too — keeps a bad token from locking you out
async def reindex(request: Request, x_admin_token: str | None = Header(default=None)):
    # Admin-only: a reindex re-embeds the whole corpus on the server and blocks /meta/ask
    # while it runs. Same gate as GET /analytics/summary — unset ADMIN_TOKEN disables it.
    admin_token = os.getenv("ADMIN_TOKEN", "")
    if not admin_token:
        raise HTTPException(status_code=403, detail="reindex disabled")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, admin_token):
        raise HTTPException(status_code=403, detail="invalid admin token")
    if not rag_service.is_available():
        raise HTTPException(status_code=503, detail=UNAVAILABLE_DETAIL)
    try:
        return await run_in_threadpool(rag_service.reindex)
    except HTTPException:
        raise
    except Exception as e:
        raise upstream_to_http(e, "meta.reindex")
