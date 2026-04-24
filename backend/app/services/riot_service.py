import os
from pathlib import Path
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


# OFFICIAL RIOT API (Pending production key approval, currently using a development key with limited access)
#RIOT_API_KEY = os.getenv("RIOT_API_KEY")

#async def get_account_by_riot_id(game_name: str, tag_line: str, region: str = "americas"):
#    url = f"https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
#    headers = {"X-Riot-Token": RIOT_API_KEY}
#    
#    async with httpx.AsyncClient() as client:
#        response = await client.get(url, headers=headers)
#        response.raise_for_status()
#        return response.json()
#
#async def get_match_history(puuid: str, region: str = "americas", count: int = 5):
#    url = f"https://{region}.api.riotgames.com/val/match/v1/matchlists/by-puuid/{puuid}"
#    headers = {"X-Riot-Token": RIOT_API_KEY}
#    
#    async with httpx.AsyncClient() as client:
#        response = await client.get(url, headers=headers)
#        response.raise_for_status()
#        return response.json()


# ---- HENRIK UNOFFICIAL RIOT API (active)

HENRIK_API_KEY = os.getenv("RIOT_API_KEY")
HENRIK_BASE_URL = "https://api.henrikdev.xyz/valorant"

async def get_account_by_riot_id(game_name: str, tag_line: str):
    url = f"{HENRIK_BASE_URL}/v1/account/{quote(game_name, safe='')}/{quote(tag_line, safe='')}"
    headers = {"Authorization": HENRIK_API_KEY}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

async def get_match_history(game_name: str, tag_line: str, region: str = "na", size: int = 3):
    url = f"{HENRIK_BASE_URL}/v3/matches/{quote(region, safe='')}/{quote(game_name, safe='')}/{quote(tag_line, safe='')}"
    headers = {"Authorization": HENRIK_API_KEY}
    params = {"size": size}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()


def summarize_matches(raw_matches: dict, game_name: str, tag_line: str) -> list:
    summaries = []
    for match in raw_matches.get("data", []):
        meta = match.get("metadata", {})
        players = match.get("players", {}).get("all_players", [])

        me = next(
            (p for p in players
             if p.get("name", "").lower() == game_name.lower()
             and p.get("tag", "").lower() == tag_line.lower()),
            None,
        )
        if not me:
            continue

        stats = me.get("stats", {})
        shots = stats.get("headshots", 0) + stats.get("bodyshots", 0) + stats.get("legshots", 0)
        hs_pct = round(stats.get("headshots", 0) / shots * 100, 1) if shots else 0.0

        team = me.get("team", "").lower()
        won = match.get("teams", {}).get(team, {}).get("has_won", False)

        summaries.append({
            "match_id": meta.get("matchid"),
            "map": meta.get("map"),
            "mode": meta.get("mode"),
            "started_at": meta.get("game_start_patched"),
            "agent": me.get("character"),
            "tier": me.get("currenttier_patched"),
            "kills": stats.get("kills"),
            "deaths": stats.get("deaths"),
            "assists": stats.get("assists"),
            "headshot_percent": hs_pct,
            "score": stats.get("score"),
            "won": won,
        })
    return summaries