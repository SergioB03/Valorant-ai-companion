import logging

import httpx
from fastapi import HTTPException

from app.alerts import notify_error
from app.budget import BudgetExceeded

logger = logging.getLogger(__name__)

def upstream_to_http(e: Exception, context: str = "request") -> HTTPException:
    # Hitting the daily spend ceiling is the breaker working as designed, not a
    # crash — so it returns 503 and deliberately does NOT fire a Discord alert
    # for every subsequent request (budget.py already logs a warning once when
    # the threshold is crossed).
    if isinstance(e, BudgetExceeded):
        return HTTPException(
            503,
            "AI features are paused for today — this app's daily usage budget has "
            "been reached. They'll be back tomorrow.",
        )
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        logger.warning("Upstream error (%s): %s -> %s", context, e.request.url.host, code)
        if code in (401, 403):
            return HTTPException(502, "The Riot data provider rejected our API key. Check RIOT_API_KEY (HenrikDev key).")
        if code == 404:
            return HTTPException(404, "Player not found. Check the name, tag, and region.")
        if code == 429:
            return HTTPException(429, "The Riot data provider is rate limiting us. Try again in a minute.")
        return HTTPException(502, f"The Riot data provider returned an error ({code}).")
    if isinstance(e, httpx.HTTPError):
        logger.warning("Upstream unreachable (%s): %s", context, e)
        return HTTPException(504, "Could not reach the Riot data provider. Try again shortly.")
    # Unexpected server-side failure: log the full traceback and alert the operator.
    logger.exception("Unhandled server error (%s)", context, exc_info=e)
    notify_error(context, e)
    return HTTPException(500, "Internal server error.")
