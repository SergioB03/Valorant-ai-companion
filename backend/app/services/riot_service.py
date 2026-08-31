import os
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


# ---- HENRIK UNOFFICIAL RIOT API (active)

# The provider is HenrikDev, not Riot. The variable was named RIOT_API_KEY back
# when the official Riot API was still the plan; that plan is gone, so the new
# name is canonical. The old one is still accepted because production reads its
# environment from SSM (/vac/*) via infra/deploy.sh -- renaming the parameter and
# the code in one step would break the running app between the two. Add
# /vac/HENRIK_API_KEY, deploy, then delete /vac/RIOT_API_KEY and this fallback.
HENRIK_API_KEY = os.getenv("HENRIK_API_KEY") or os.getenv("RIOT_API_KEY")
HENRIK_BASE_URL = "https://api.henrikdev.xyz/valorant"


async def _henrik_get(url: str, params: dict | None = None):
    """GET with one automatic retry on transient failures (network errors / upstream 5xx)."""
    if not HENRIK_API_KEY:
        raise RuntimeError("HENRIK_API_KEY is not set (legacy name: RIOT_API_KEY)")
    headers = {"Authorization": HENRIK_API_KEY}
    async with httpx.AsyncClient(timeout=15.0) as client:
        for attempt in (1, 2):
            try:
                response = await client.get(url, headers=headers, params=params)
                if response.status_code >= 500 and attempt == 1:
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.TransportError:
                if attempt == 2:
                    raise

async def get_account_by_riot_id(game_name: str, tag_line: str):
    url = f"{HENRIK_BASE_URL}/v1/account/{quote(game_name, safe='')}/{quote(tag_line, safe='')}"
    return await _henrik_get(url)

async def get_match_history(game_name: str, tag_line: str, region: str = "na", size: int = 3, mode: str | None = None):
    # Clamped at the chokepoint rather than per-route: HenrikDev bills each
    # background Riot request against our key's bucket, so an unclamped ?size=
    # from any caller could burn the whole budget in one request. Every route
    # reaches upstream through here.
    size = max(1, min(int(size), 10))
    url = f"{HENRIK_BASE_URL}/v3/matches/{region}/{quote(game_name, safe='')}/{quote(tag_line, safe='')}"
    params = {"size": size}
    if mode:
        params["mode"] = mode
    return await _henrik_get(url, params)


def summarize_matches(raw_matches: dict, game_name: str, tag_line: str) -> list:
    summaries = []
    for match in raw_matches.get("data") or []:
        # Henrik sometimes returns matches it couldn't hydrate: metadata/players/teams are null.
        if not match:
            continue
        meta = match.get("metadata") or {}
        players = (match.get("players") or {}).get("all_players") or []

        me = next(
            (p for p in players
             if p.get("name", "").lower() == game_name.lower()
             and p.get("tag", "").lower() == tag_line.lower()),
            None,
        )
        if not me:
            continue

        stats = me.get("stats") or {}
        shots = (stats.get("headshots") or 0) + (stats.get("bodyshots") or 0) + (stats.get("legshots") or 0)
        hs_pct = round((stats.get("headshots") or 0) / shots * 100, 1) if shots else 0.0

        team = (me.get("team") or "").lower()
        won = ((match.get("teams") or {}).get(team) or {}).get("has_won", False)

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