from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.claude_service import ask_claude, analyze_matches
from app.services.riot_service import get_match_history, summarize_matches

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
        raw = await get_match_history(game_name, tag_line, region)
        summaries = summarize_matches(raw, game_name, tag_line)
        if not summaries:
            raise HTTPException(status_code=404, detail="No matches found for that name/tag")
        analysis = analyze_matches(summaries)
        return {"analysis": analysis, "match_count": len(summaries)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))