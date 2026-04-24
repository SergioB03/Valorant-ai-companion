import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.limiter import limiter
from app.services.claude_service import ask_claude, analyze_matches, stream_analysis
from app.services.riot_service import get_match_history, summarize_matches

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/claude", tags=["claude"])


class PromptRequest(BaseModel):
    prompt: str


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


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


@router.get("/analyze/stream/{game_name}/{tag_line}")
@limiter.limit("10/minute")
async def analyze_stream(request: Request, game_name: str, tag_line: str, region: str = "na"):
    async def event_stream():
        try:
            yield _sse("progress", {"stage": "fetching_matches"})
            raw = await get_match_history(game_name, tag_line, region)
            summaries = summarize_matches(raw, game_name, tag_line)

            if not summaries:
                yield _sse("error", {"message": "No matches found for that name/tag"})
                return

            yield _sse("progress", {"stage": "analyzing", "match_count": len(summaries)})

            async for token in stream_analysis(summaries):
                yield _sse("token", {"text": token})

            yield _sse("done", {"match_count": len(summaries)})
        except Exception:
            logger.exception("streaming analyze failed for %s#%s", game_name, tag_line)
            yield _sse("error", {"message": "Analysis failed"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
