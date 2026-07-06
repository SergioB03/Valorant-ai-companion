import httpx
from fastapi import HTTPException

def upstream_to_http(e: Exception) -> HTTPException:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code in (401, 403):
            return HTTPException(502, "The Riot data provider rejected our API key. Check RIOT_API_KEY (HenrikDev key).")
        if code == 404:
            return HTTPException(404, "Player not found. Check the name, tag, and region.")
        if code == 429:
            return HTTPException(429, "The Riot data provider is rate limiting us. Try again in a minute.")
        return HTTPException(502, f"The Riot data provider returned an error ({code}).")
    if isinstance(e, httpx.HTTPError):
        return HTTPException(504, "Could not reach the Riot data provider. Try again shortly.")
    return HTTPException(500, "Internal server error.")
