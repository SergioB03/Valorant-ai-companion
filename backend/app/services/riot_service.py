import os
import httpx
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

RIOT_API_KEY = os.getenv("RIOT_API_KEY")

async def get_account_by_riot_id(game_name: str, tag_line: str, region: str = "americas"):
    url = f"https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

async def get_match_history(puuid: str, region: str = "americas", count: int = 5):
    url = f"https://{region}.api.riotgames.com/val/match/v1/matchlists/by-puuid/{puuid}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()