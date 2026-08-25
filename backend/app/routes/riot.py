from fastapi import APIRouter, HTTPException, Request
from app.errors import upstream_to_http
from app.limiter import limiter
from app.services.riot_service import get_account_by_riot_id, get_match_history, summarize_matches

router = APIRouter(prefix="/riot", tags=["riot"])

# These two are the only routes that reach the Riot data provider without a
# Claude call, so they were easy to overlook — but each one still spends from
# our upstream key's quota (HenrikDev counts every background Riot request it
# makes on our behalf). Unlimited, they were the cheapest way to exhaust that
# key and take every other feature down with it. `request: Request` is required
# by slowapi: without it the decorator raises at import time.


@router.get("/account/{game_name}/{tag_line}")
@limiter.limit("20/minute")
async def get_account(request: Request, game_name: str, tag_line: str):
    try:
        account = await get_account_by_riot_id(game_name, tag_line)
        return account
    except HTTPException:
        raise
    except Exception as e:
        raise upstream_to_http(e, "riot.account")

@router.get("/matches/{game_name}/{tag_line}")
@limiter.limit("20/minute")
async def get_matches(request: Request, game_name: str, tag_line: str, region: str = "na", size: int = 3):
    try:
        raw = await get_match_history(game_name, tag_line, region, size)
        return summarize_matches(raw, game_name, tag_line)
    except HTTPException:
        raise
    except Exception as e:
        raise upstream_to_http(e, "riot.matches")
