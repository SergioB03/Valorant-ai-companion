import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.limiter import limiter
from app.services.mental_service import coach, detect_tilt_signals, stream_coach
from app.services.riot_service import get_match_history, summarize_matches

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mental", tags=["mental"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/coach/{game_name}/{tag_line}")
@limiter.limit("10/minute")
async def coach_endpoint(
    request: Request, game_name: str, tag_line: str, region: str = "na", size: int = 10
):
    try:
        raw = await get_match_history(game_name, tag_line, region, size)
        matches = summarize_matches(raw, game_name, tag_line)
        if not matches:
            raise HTTPException(status_code=404, detail="No matches found for that name/tag")

        signals = detect_tilt_signals(matches)
        coaching = coach(matches, signals)
        return {"signals": signals, "coaching": coaching, "match_count": len(matches)}
    except HTTPException:
        raise
    except Exception:
        logger.exception("coach failed for %s#%s", game_name, tag_line)
        raise HTTPException(status_code=502, detail="Could not generate coaching")


@router.get("/coach/stream/{game_name}/{tag_line}")
@limiter.limit("10/minute")
async def coach_stream(
    request: Request, game_name: str, tag_line: str, region: str = "na", size: int = 10
):
    async def event_stream():
        try:
            yield _sse("progress", {"stage": "fetching_matches"})
            raw = await get_match_history(game_name, tag_line, region, size)
            matches = summarize_matches(raw, game_name, tag_line)

            if not matches:
                yield _sse("error", {"message": "No matches found for that name/tag"})
                return

            yield _sse("progress", {"stage": "detecting_patterns", "match_count": len(matches)})
            signals = detect_tilt_signals(matches)
            yield _sse("signals", signals)

            yield _sse("progress", {"stage": "coaching"})
            async for token in stream_coach(matches, signals):
                yield _sse("token", {"text": token})

            yield _sse("done", {"match_count": len(matches)})
        except Exception:
            logger.exception("streaming coach failed for %s#%s", game_name, tag_line)
            yield _sse("error", {"message": "Coaching failed"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
