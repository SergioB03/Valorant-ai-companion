"""A hard daily ceiling on Anthropic spend.

Per-IP rate limits cap how fast *one* visitor can spend; they do not cap the
total. Anyone willing to rotate IPs could still run the bill up, and a bug in
our own code could too. This is the backstop that does not care where the
traffic came from: once the day's estimated spend crosses DAILY_BUDGET_USD,
every Claude-backed endpoint returns 503 until UTC midnight.

Spend is *estimated* from the token counts Anthropic returns on each response,
priced from the table below. It will not match the invoice to the cent — it is
a circuit breaker, not an accounting system. Set the authoritative limit in the
Anthropic console too; that one no bug of ours can defeat.

Where the counters live is decided by app/budget_store.py: SQLite by default,
DynamoDB when BUDGET_TABLE_NAME is set. SQLite is correct on one instance and
silently wrong on two -- each would hold its own total, so the cap would
multiply by the instance count, and a deploy onto fresh storage would reset the
day's spend to zero. The shared store is what makes more than one instance safe.

Both check functions fail *closed*: if the counters cannot be read we cannot
prove we are under the ceiling, and a brief 503 is cheaper than an unbounded
bill.
"""

import hashlib
import logging
import os
from datetime import datetime, timezone

from app.alerts import DOWN, notify_alert
from app.budget_store import get_store

logger = logging.getLogger(__name__)

# USD per million tokens (input, output). Output includes thinking tokens.
_PRICES = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
# Unknown model ids fall back to the most expensive rate we know, so a typo in
# CLAUDE_MODEL can never make the breaker *under*-count.
_FALLBACK_PRICE = (10.0, 50.0)


class BudgetExceeded(Exception):
    """Raised instead of calling Claude once the daily ceiling is reached."""


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def daily_budget_usd() -> float:
    try:
        return float(os.getenv("DAILY_BUDGET_USD", "5.00"))
    except ValueError:
        return 5.00


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = _PRICES.get(model, _FALLBACK_PRICE)
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


def spent_today() -> float:
    return get_store().spent_today(_today())


def check_budget() -> None:
    """Raise BudgetExceeded if today's spend has already hit the ceiling."""
    budget = daily_budget_usd()
    if budget <= 0:
        return  # 0 or negative disables the breaker
    try:
        spent = spent_today()
    except Exception as exc:
        # Cannot read the counter => cannot prove we are under budget. Refusing
        # is recoverable; an unbounded bill is not.
        logger.exception("budget counter unreadable - refusing the call")
        notify_alert(
            "🛑 Budget counter unreadable — AI features are OFF",
            "The spend counter could not be read, so Claude-backed endpoints "
            "are returning 503 rather than risk spending past the cap blind.",
            key="budget:store-down",
            window=3600,
            color=DOWN,
        )
        raise BudgetExceeded("spend counter unavailable") from exc
    if spent >= budget:
        logger.warning("Daily Claude budget reached: $%.4f of $%.2f", spent, budget)
        notify_alert(
            "🛑 AI features are OFF — daily budget spent",
            f"Spent **${spent:.2f}** of the ${budget:.2f} daily cap, so every "
            "Claude-backed endpoint is returning 503 until 00:00 UTC.\n\n"
            "Raise `DAILY_BUDGET_USD` to restore service sooner, or leave it "
            "if this is someone abusing the app.",
            key="budget:exhausted",
            window=6 * 3600,
            color=DOWN,
        )
        raise BudgetExceeded(f"daily budget ${budget:.2f} reached")


# --- Per-visitor share of the daily budget -----------------------------------
#
# The global cap above stops the bill running away, but on its own it is a
# denial-of-service vector: the per-minute rate limits still allow ~50 AI calls
# a minute from ONE address, which drains a $5 day in about eight and a half
# minutes and leaves every other visitor with 503s until UTC midnight. A cost
# control that one person can trip for everybody is not much of a control.
#
# So each source also gets its own daily allowance underneath the global cap.
# Normal use is a handful of actions per visit; the default here is far above
# that and still far below what an attacker needs.


class QuotaExceeded(Exception):
    """Raised when one source has used its own daily allowance."""


def daily_ip_quota() -> int:
    try:
        return int(os.getenv("FREE_AI_ACTIONS_PER_IP_PER_DAY", "40"))
    except ValueError:
        return 40


def _ip_key(ip: str) -> str:
    """Store a salted hash, never the address itself.

    The analytics tables deliberately hold no IPs (see ANALYTICS.md) and this
    must not be the thing that reintroduces them. The salt is per-day, so the
    hashes are not linkable across days even if the database leaks.
    """
    return hashlib.sha256(f"{_today()}:{ip}".encode()).hexdigest()[:32]


def check_ip_quota(ip: str) -> None:
    quota = daily_ip_quota()
    if quota <= 0:
        return
    try:
        calls = get_store().ip_calls(_today(), _ip_key(ip))
    except Exception as exc:
        # Same reasoning as check_budget: unreadable counters mean we cannot
        # show this caller is within their share.
        logger.exception("per-source counter unreadable - refusing the call")
        raise QuotaExceeded("usage counter unavailable") from exc
    if calls >= quota:
        raise QuotaExceeded(f"daily limit of {quota} AI actions reached")


def record_ip_use(ip: str) -> None:
    try:
        get_store().record_ip(_today(), _ip_key(ip))
    except Exception:
        # Bookkeeping must not fail a request that already succeeded. The
        # global ceiling is the control that actually bounds the bill.
        logger.warning("could not record per-source usage", exc_info=True)


def record_spend(model: str, input_tokens: int, output_tokens: int) -> float:
    """Add one call's estimated cost to today's total. Returns the new total."""
    cost = estimate_cost_usd(model, input_tokens, output_tokens)
    try:
        total = get_store().add_spend(_today(), cost)
    except Exception:
        # The call already happened and the money is already spent. Losing the
        # record is bad -- it under-counts the day -- but raising here would
        # turn a successful response into an error for the user as well.
        logger.exception("could not record spend - the day's total is now low")
        return cost
    budget = daily_budget_usd()
    # Warn while there is still headroom, so the operator hears about it before
    # users start seeing 503s.
    if budget > 0 and total >= budget * 0.8 > (total - cost):
        logger.warning(
            "Claude spend at %.0f%% of the daily budget ($%.4f of $%.2f)",
            total / budget * 100, total, budget,
        )
        notify_alert(
            "⚠️ Claude spend at 80% of today's budget",
            f"**${total:.2f}** of ${budget:.2f} used. At this rate the AI "
            "features will start returning 503 before the day is out.",
            key="budget:80pct",
            window=6 * 3600,
        )
    return total


def status() -> dict:
    budget = daily_budget_usd()
    spent = spent_today()
    return {
        "day": _today(),
        "spent_usd": round(spent, 4),
        "budget_usd": budget,
        "remaining_usd": round(max(0.0, budget - spent), 4) if budget > 0 else None,
        "enabled": budget > 0,
    }
