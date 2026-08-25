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

State lives in the same SQLite file as everything else, so this adds no
infrastructure and survives restarts. On a single instance that is sufficient;
running more than one would need a shared counter.
"""

import hashlib
import logging
import os
import threading
from datetime import datetime, timezone

from app.db import get_conn

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

_lock = threading.Lock()


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
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT cost_usd FROM claude_spend WHERE day = ?", (_today(),)
        ).fetchone()
        return float(row["cost_usd"]) if row else 0.0
    finally:
        conn.close()


def check_budget() -> None:
    """Raise BudgetExceeded if today's spend has already hit the ceiling."""
    budget = daily_budget_usd()
    if budget <= 0:
        return  # 0 or negative disables the breaker
    spent = spent_today()
    if spent >= budget:
        logger.warning("Daily Claude budget reached: $%.4f of $%.2f", spent, budget)
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
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT calls FROM ip_usage WHERE day = ? AND ip_key = ?",
            (_today(), _ip_key(ip)),
        ).fetchone()
    finally:
        conn.close()
    if row and int(row["calls"]) >= quota:
        raise QuotaExceeded(f"daily limit of {quota} AI actions reached")


def record_ip_use(ip: str) -> None:
    day, key = _today(), _ip_key(ip)
    with _lock:
        conn = get_conn()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO ip_usage (day, ip_key, calls) VALUES (?, ?, 1) "
                    "ON CONFLICT(day, ip_key) DO UPDATE SET calls = calls + 1",
                    (day, key),
                )
                # Yesterday's rows are dead weight; drop them opportunistically
                # so this table cannot grow without bound under IP rotation.
                conn.execute("DELETE FROM ip_usage WHERE day < ?", (day,))
        finally:
            conn.close()


def record_spend(model: str, input_tokens: int, output_tokens: int) -> float:
    """Add one call's estimated cost to today's total. Returns the new total."""
    cost = estimate_cost_usd(model, input_tokens, output_tokens)
    day = _today()
    with _lock:
        conn = get_conn()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO claude_spend (day, cost_usd, calls) VALUES (?, ?, 1) "
                    "ON CONFLICT(day) DO UPDATE SET "
                    "cost_usd = cost_usd + excluded.cost_usd, calls = calls + 1",
                    (day, cost),
                )
                row = conn.execute(
                    "SELECT cost_usd FROM claude_spend WHERE day = ?", (day,)
                ).fetchone()
        finally:
            conn.close()
    total = float(row["cost_usd"]) if row else cost
    budget = daily_budget_usd()
    # Warn while there is still headroom, so the operator hears about it before
    # users start seeing 503s.
    if budget > 0 and total >= budget * 0.8 > (total - cost):
        logger.warning(
            "Claude spend at %.0f%% of the daily budget ($%.4f of $%.2f)",
            total / budget * 100, total, budget,
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
