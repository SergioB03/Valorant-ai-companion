from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from app.errors import upstream_to_http
from app.limiter import limiter
from app.services import rag_service

router = APIRouter(prefix="/meta", tags=["meta"])

UNAVAILABLE_DETAIL = (
    "Meta Q&A is unavailable: chromadb is not installed on the server. "
    "Install it with 'pip install chromadb' and restart the backend."
)

class AskRequest(BaseModel):
    question: str

@router.post("/ask")
@limiter.limit("15/minute")
async def ask(request: Request, body: AskRequest):
    if not rag_service.is_available():
        raise HTTPException(status_code=503, detail=UNAVAILABLE_DETAIL)
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")
    try:
        await run_in_threadpool(rag_service.ensure_index)
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
async def reindex():
    if not rag_service.is_available():
        raise HTTPException(status_code=503, detail=UNAVAILABLE_DETAIL)
    try:
        return await run_in_threadpool(rag_service.reindex)
    except HTTPException:
        raise
    except Exception as e:
        raise upstream_to_http(e, "meta.reindex")
