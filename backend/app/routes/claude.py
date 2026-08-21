from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from app.errors import upstream_to_http
from app.limiter import limiter
from app.services.claude_service import ask_claude, analyze_matches_structured
from app.services.riot_service import get_match_history, summarize_matches

router = APIRouter(prefix="/claude", tags=["claude"])

class PromptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)

@router.post("/ask")
@limiter.limit("5/minute")
def ask(request: Request, body: PromptRequest):
    response = ask_claude(body.prompt)
    return {"response": response}

@router.get("/analyze/{game_name}/{tag_line}")
@limiter.limit("10/minute")
async def analyze(request: Request, game_name: str, tag_line: str, region: str = "na", size: int = 10, mode: str = "competitive"):
    size = max(1, min(size, 10))
    try:
        raw = await get_match_history(game_name, tag_line, region, size, mode=mode or None)
        summaries = summarize_matches(raw, game_name, tag_line)
        if mode:
            summaries = [m for m in summaries if (m.get("mode") or "").lower() == mode.lower()]
        if not summaries:
            raise HTTPException(status_code=404, detail="No matches found for that name/tag")
        analysis = await run_in_threadpool(analyze_matches_structured, summaries)
        return {"analysis": analysis, "match_count": len(summaries)}
    except HTTPException:
        raise
    except Exception as e:
        raise upstream_to_http(e, "claude.analyze")
