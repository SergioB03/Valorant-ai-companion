"""Shared FastAPI dependencies."""

from fastapi import HTTPException, Request

from app.budget import QuotaExceeded, check_ip_quota, daily_ip_quota, record_ip_use
from app.limiter import client_ip


async def ai_quota(request: Request) -> None:
    """Charge one AI action against this source's daily allowance.

    Applied to every endpoint that spends money, so no single visitor can
    consume the whole daily budget and leave everyone else with 503s.

    The allowance is charged on entry rather than on success: a request that
    reaches Claude and then fails has already cost us, and charging only for
    successes would let someone farm failures for free.
    """
    ip = client_ip(request)
    try:
        check_ip_quota(ip)
    except QuotaExceeded:
        raise HTTPException(
            status_code=429,
            detail=(
                f"You've used your {daily_ip_quota()} AI actions for today. "
                "This keeps the app affordable for everyone — it resets at "
                "midnight UTC."
            ),
        )
    record_ip_use(ip)
