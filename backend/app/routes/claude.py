import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.limiter import limiter
from app.services.claude_service import ask_claude, analyze_matches
from app.services.riot_service import get_match_history, summarize_matches

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/claude", tags=["claude"])


class PromptRequest(BaseModel):
    prompt: str


@router.post("/ask")
@limiter.limit("3/minute")
def ask(request: Request, body: PromptRequest):
    try:
        response = ask_claude(body.prompt)
        return {"response": response}
    except Exception:
        logger.exception("ask_claude failed")
        raise HTTPException(status_code=500, detail="Claude request failed")


@router.get("/analyze/{game_name}/{tag_line}")
@limiter.limit("10/minute")
async def analyze(request: Request, game_name: str, tag_line: str, region: str = "na"):
    try:
        raw = await get_match_history(game_name, tag_line, region)
        summaries = summarize_matches(raw, game_name, tag_line)
        if not summaries:
            raise HTTPException(status_code=404, detail="No matches found for that name/tag")
        analysis = analyze_matches(summaries)
        return {"analysis": analysis, "match_count": len(summaries)}
    except HTTPException:
        raise
    except Exception:
        logger.exception("analyze failed for %s#%s", game_name, tag_line)
        raise HTTPException(status_code=502, detail="Could not analyze matches")
