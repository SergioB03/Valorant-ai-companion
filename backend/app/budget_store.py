"""Storage for the two counters that guard money and abuse.

These live apart from db.py because they have a different requirement from the
rest of the data. Tilt snapshots and analytics are read-mostly and want SQL
aggregation; the spend total and the per-source allowance are high-write
counters whose *correctness under concurrency* is the whole point. A cost
control that loses increments is not a cost control.

Two backends behind one interface:

  SQLite   - default. Correct for a single instance, which is what runs today.
  DynamoDB - used when BUDGET_TABLE_NAME is set. Atomic ADD means concurrent
             writers cannot lose an increment, and the counters live off the
             instance, so they survive its loss and are shared by every replica.

The SQLite counters are per-instance and per-disk. That is fine on one EC2 box
and silently wrong the moment a second one exists: each would keep its own
spend total, so the daily cap would multiply by the instance count, and every
deploy onto fresh storage would reset the day's spend to zero. Moving these two
counters is therefore the precondition for running more than one instance --
not an optimisation.
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

# Two days, so a counter is readable for a while after its day rolls over and
# then reaps itself. Replaces the opportunistic DELETE the SQLite path does.
_TTL_SECONDS = 60 * 60 * 48


class BudgetStoreUnavailable(Exception):
    """The counters could not be read. Callers must fail closed."""


class SqliteStore:
    """Single-instance counters, backed by the existing companion.sqlite3."""

    name = "sqlite"

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def spent_today(self, day: str) -> float:
        from app.db import get_conn

        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT cost_usd FROM claude_spend WHERE day = ?", (day,)
            ).fetchone()
            return float(row["cost_usd"]) if row else 0.0
        finally:
            conn.close()

    def add_spend(self, day: str, cost: float) -> float:
        from app.db import get_conn

        with self._lock:
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
        return float(row["cost_usd"]) if row else cost

    def ip_calls(self, day: str, ip_key: str) -> int:
        from app.db import get_conn

        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT calls FROM ip_usage WHERE day = ? AND ip_key = ?", (day, ip_key)
            ).fetchone()
            return int(row["calls"]) if row else 0
        finally:
            conn.close()

    def record_ip(self, day: str, ip_key: str) -> None:
        from app.db import get_conn

        with self._lock:
            conn = get_conn()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO ip_usage (day, ip_key, calls) VALUES (?, ?, 1) "
                        "ON CONFLICT(day, ip_key) DO UPDATE SET calls = calls + 1",
                        (day, ip_key),
                    )
                    # Yesterday's rows are dead weight; drop them opportunistically
                    # so this table cannot grow without bound under IP rotation.
                    conn.execute("DELETE FROM ip_usage WHERE day < ?", (day,))
            finally:
                conn.close()


class DynamoStore:
    """Shared counters in one DynamoDB table.

    Schema: partition key `pk` (String), a Number attribute per counter, and a
    `ttl` Number registered as the table's TTL attribute so day-buckets expire
    without a cleanup job.

    Every write is an atomic ADD. Read-modify-write from several tasks would
    lose increments under exactly the traffic the cap exists to survive.
    """

    name = "dynamodb"

    def __init__(self, table_name: str, region: str) -> None:
        import boto3
        from botocore.config import Config

        self._table = boto3.resource(
            "dynamodb",
            region_name=region,
            # Short timeouts: this sits in the request path, and a hung metadata
            # call would stall the endpoint it is meant to protect.
            config=Config(
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=2,
                read_timeout=3,
            ),
        ).Table(table_name)

    def _add(self, pk: str, attr: str, amount) -> float:
        from decimal import Decimal

        result = self._table.update_item(
            Key={"pk": pk},
            UpdateExpression=f"ADD #a :amt SET #ttl = :ttl",
            ExpressionAttributeNames={"#a": attr, "#ttl": "ttl"},
            ExpressionAttributeValues={
                ":amt": Decimal(str(amount)),
                ":ttl": int(time.time()) + _TTL_SECONDS,
            },
            ReturnValues="UPDATED_NEW",
        )
        return float(result["Attributes"][attr])

    def _get(self, pk: str, attr: str) -> float:
        # Strongly consistent: an eventually-consistent read could report a
        # stale total and wave through spend that is already over the cap.
        item = self._table.get_item(Key={"pk": pk}, ConsistentRead=True).get("Item")
        return float(item[attr]) if item and attr in item else 0.0

    def spent_today(self, day: str) -> float:
        return self._get(f"spend#{day}", "cost_usd")

    def add_spend(self, day: str, cost: float) -> float:
        total = self._add(f"spend#{day}", "cost_usd", cost)
        try:
            self._add(f"spend#{day}", "calls", 1)
        except Exception:
            logger.warning("could not increment call count", exc_info=True)
        return total

    def ip_calls(self, day: str, ip_key: str) -> int:
        return int(self._get(f"ip#{day}#{ip_key}", "calls"))

    def record_ip(self, day: str, ip_key: str) -> None:
        self._add(f"ip#{day}#{ip_key}", "calls", 1)


_store = None
_store_lock = threading.Lock()


def get_store():
    """The process-wide counter store, chosen once from the environment."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                table = os.getenv("BUDGET_TABLE_NAME", "").strip()
                if table:
                    _store = DynamoStore(table, os.getenv("AWS_REGION", "us-east-1"))
                    logger.info("budget counters: dynamodb table=%s", table)
                else:
                    _store = SqliteStore()
                    logger.info(
                        "budget counters: sqlite (per-instance). Set "
                        "BUDGET_TABLE_NAME to share them across instances."
                    )
    return _store


def reset_store_for_tests() -> None:
    global _store
    _store = None
