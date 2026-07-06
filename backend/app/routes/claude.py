from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from app.errors import upstream_to_http
from app.services.claude_service import ask_claude, analyze_matches
from app.services.riot_service import get_match_history, summarize_matches

router = APIRouter(prefix="/claude", tags=["claude"])

class PromptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)

@router.post("/ask")
def ask(request: PromptRequest):
    response = ask_claude(request.prompt)
    return {"response": response}

@router.get("/analyze/{game_name}/{tag_line}")
async def analyze(game_name: str, tag_line: str, region: str = "na", size: int = 10):
    size = max(1, min(size, 10))
    try:
        raw = await get_match_history(game_name, tag_line, region, size)
        summaries = summarize_matches(raw, game_name, tag_line)
        if not summaries:
            raise HTTPException(status_code=404, detail="No matches found for that name/tag")
        analysis = await run_in_threadpool(analyze_matches, summaries)
        return {"analysis": analysis, "match_count": len(summaries)}
    except HTTPException:
        raise
    except Exception as e:
        raise upstream_to_http(e)
