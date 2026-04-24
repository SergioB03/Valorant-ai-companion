import logging

from fastapi import APIRouter, HTTPException, Request

from app.limiter import limiter
from app.services.riot_service import get_account_by_riot_id, get_match_history, summarize_matches

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/riot", tags=["riot"])


@router.get("/account/{game_name}/{tag_line}")
@limiter.limit("20/minute")
async def get_account(request: Request, game_name: str, tag_line: str):
    try:
        return await get_account_by_riot_id(game_name, tag_line)
    except Exception:
        logger.exception("account lookup failed for %s#%s", game_name, tag_line)
        raise HTTPException(status_code=502, detail="Could not fetch account")


@router.get("/matches/{game_name}/{tag_line}")
@limiter.limit("20/minute")
async def get_matches(request: Request, game_name: str, tag_line: str, region: str = "na", size: int = 3):
    try:
        raw = await get_match_history(game_name, tag_line, region, size)
        return summarize_matches(raw, game_name, tag_line)
    except Exception:
        logger.exception("match history failed for %s#%s", game_name, tag_line)
        raise HTTPException(status_code=502, detail="Could not fetch match history")
