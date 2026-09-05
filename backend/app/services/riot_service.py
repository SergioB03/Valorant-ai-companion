import os
import time
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


# ---- In-process TTL cache for HenrikDev responses.
#
# Why: /claude/analyze, /mental/tilt-check and /mental/coach each fetch the same
# player's match history with effectively identical params, so one user touring
# the tabs burns 3-4 upstream calls returning identical data — against a
# 30 req/min key where HenrikDev bills the background Riot calls too
# (ARCHITECTURE.md recommendation #1). Accounts barely change (10 min TTL);
# match history only changes when a ~30-min game finishes (2 min TTL keeps a
# post-game refresh snappy while still absorbing the tab tour).
#
# A plain dict is safe here: uvicorn runs a single process with a single event
# loop (no --workers in the Dockerfile CMD) and there is no await between the
# check and the insert. Keyed on the full URL + sorted params, so any variance
# (size, mode, region) is a different entry — never a wrong-shape hit.
# Timestamps use time.monotonic(), immune to wall-clock jumps.
#
# Cached payloads are shared between callers and must be treated as read-only;
# every current caller only reads (summarize_matches builds new dicts).
_CACHE: dict[tuple, tuple[float, object]] = {}
_CACHE_MAX = 256          # ~a few KB per entry; hard cap so memory is bounded
ACCOUNT_TTL = 600.0       # 10 min
MATCHES_TTL = 120.0       # 2 min


def _cache_get(key: tuple):
    hit = _CACHE.get(key)
    if hit is None:
        return None
    expires_at, payload = hit
    if time.monotonic() >= expires_at:
        _CACHE.pop(key, None)
        return None
    return payload


def _cache_put(key: tuple, payload, ttl: float) -> None:
    now = time.monotonic()
    if len(_CACHE) >= _CACHE_MAX:
        # Drop everything already expired first; if still full, evict oldest
        # inserted (dicts preserve insertion order) until under the cap.
        for k in [k for k, (exp, _) in _CACHE.items() if exp <= now]:
            _CACHE.pop(k, None)
        while len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = (now + ttl, payload)


async def _henrik_get(url: str, params: dict | None = None, ttl: float | None = None):
    """GET with one automatic retry on transient failures (network errors / upstream 5xx).

    When ttl is given, successful JSON payloads are served from / stored in the
    in-process TTL cache. Errors are never cached.
    """
    if not HENRIK_API_KEY:
        raise RuntimeError("HENRIK_API_KEY is not set (legacy name: RIOT_API_KEY)")
    key = (url, tuple(sorted((params or {}).items())))
    if ttl is not None:
        cached = _cache_get(key)
        if cached is not None:
            return cached
    headers = {"Authorization": HENRIK_API_KEY}
    async with httpx.AsyncClient(timeout=15.0) as client:
        for attempt in (1, 2):
            try:
                response = await client.get(url, headers=headers, params=params)
                if response.status_code >= 500 and attempt == 1:
                    continue
                response.raise_for_status()
                payload = response.json()
                if ttl is not None:
                    _cache_put(key, payload, ttl)
                return payload
            except httpx.TransportError:
                if attempt == 2:
                    raise

async def get_account_by_riot_id(game_name: str, tag_line: str):
    url = f"{HENRIK_BASE_URL}/v1/account/{quote(game_name, safe='')}/{quote(tag_line, safe='')}"
    return await _henrik_get(url, ttl=ACCOUNT_TTL)

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
    return await _henrik_get(url, params, ttl=MATCHES_TTL)


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