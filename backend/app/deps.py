"""Shared FastAPI dependencies."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response

from app.budget import QuotaExceeded, check_ip_quota, daily_ip_quota, record_ip_use
from app.limiter import client_ip


def seconds_to_utc_midnight() -> int:
    """Seconds until the daily allowance resets (00:00 UTC). Never below 1."""
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - now).total_seconds()))


async def ai_quota(request: Request, response: Response) -> None:
    """Charge one AI action against this source's daily allowance.

    Applied to every endpoint that spends money, so no single visitor can
    consume the whole daily budget and leave everyone else with 503s.

    The allowance is charged on entry rather than on success: a request that
    reaches Claude and then fails has already cost us, and charging only for
    successes would let someone farm failures for free.

    Headers are the interface the frontend keys its quota UI on:
    - Successful responses carry ``X-Quota-Limit`` so the "free daily AI
      actions" caption never hardcodes the number (it is env-configurable).
    - The quota 429 additionally carries ``X-Quota-Exhausted: 1`` — the ONLY
      signal for the friendly "out of free AI actions" state, because three
      different 429s exist (this one, slowapi's per-minute limit, and Henrik
      upstream) — plus ``Retry-After`` with the seconds to UTC midnight.
    """
    limit = daily_ip_quota()
    # Set on the injected Response so FastAPI merges it into successful
    # responses; error responses are built by exception handlers and do not
    # inherit it (the 429 below carries its own copy). 0 disables the quota
    # entirely, in which case advertising a limit of 0 would be a lie.
    if limit > 0:
        response.headers["X-Quota-Limit"] = str(limit)
    ip = client_ip(request)
    try:
        check_ip_quota(ip)
    except QuotaExceeded:
        raise HTTPException(
            status_code=429,
            detail=(
                f"You've used your {limit} AI actions for today. "
                "This keeps the app affordable for everyone — it resets at "
                "midnight UTC."
            ),
            headers={
                "X-Quota-Exhausted": "1",
                "Retry-After": str(seconds_to_utc_midnight()),
                "X-Quota-Limit": str(limit),
            },
        )
    record_ip_use(ip)
