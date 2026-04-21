from fastapi import APIRouter, HTTPException
from app.services.riot_service import get_account_by_riot_id, get_match_history

router = APIRouter(prefix="/riot", tags=["riot"])

@router.get("/account/{game_name}/{tag_line}")
async def get_account(game_name: str, tag_line: str):
    try:
        account = await get_account_by_riot_id(game_name, tag_line)
        return account
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/matches/{game_name}/{tag_line}")
async def get_matches(game_name: str, tag_line: str):
    try:
        account = await get_account_by_riot_id(game_name, tag_line)
        puuid = account["puuid"]
        matches = await get_match_history(puuid)
        return matches
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))