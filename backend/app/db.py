import json
import math
import os
import sqlite3
import threading
from pathlib import Path

# VAC_STATE_DIR lets a deployment point the mutable state (SQLite) at a persistent
# volume; unset, it sits next to the knowledge files in backend/data/ as before.
_STATE_DIR = Path(os.getenv("VAC_STATE_DIR") or Path(__file__).resolve().parents[1] / "data")
DB_PATH = _STATE_DIR / "companion.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tilt_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    riot_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    tilt_score INTEGER,
    tilt_level TEXT,
    matches_analyzed INTEGER,
    report_json TEXT
);

CREATE TABLE IF NOT EXISTS coach_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    riot_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    user_message TEXT,
    coach_reply TEXT
);

CREATE TABLE IF NOT EXISTS analytics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visitor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    name TEXT NOT NULL,
    path TEXT,
    props_json TEXT,
    client_ts INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_analytics_events_name_created
    ON analytics_events (name, created_at);
CREATE INDEX IF NOT EXISTS idx_analytics_events_visitor
    ON analytics_events (visitor_id);

-- One row per UTC day holding the day's estimated Anthropic spend. Read and
-- written by app/budget.py, which refuses further Claude calls once the day's
-- total reaches DAILY_BUDGET_USD.
CREATE TABLE IF NOT EXISTS claude_spend (
    day TEXT PRIMARY KEY,
    cost_usd REAL NOT NULL DEFAULT 0,
    calls INTEGER NOT NULL DEFAULT 0
);
"""

# Runs once per process alongside SCHEMA. Earlier versions stored the text of
# coach conversations against the searched Riot ID, where anyone could read it
# back via GET /mental/profile. Nothing writes those columns any more, and this
# clears anything an existing database still holds.
MIGRATIONS = """
UPDATE coach_sessions SET user_message = NULL, coach_reply = NULL
    WHERE user_message IS NOT NULL OR coach_reply IS NOT NULL;
"""


_initialized = False
_init_lock = threading.Lock()


def get_conn() -> sqlite3.Connection:
    global _initialized
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    if not _initialized:
        with _init_lock:
            if not _initialized:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript(SCHEMA)
                conn.executescript(MIGRATIONS)
                _initialized = True
    return conn


def save_snapshot(riot_id: str, report: dict):
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                "INSERT INTO tilt_snapshots (riot_id, tilt_score, tilt_level, matches_analyzed, report_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    riot_id,
                    report.get("tilt_score"),
                    report.get("tilt_level"),
                    report.get("matches_analyzed"),
                    json.dumps(report),
                ),
            )
    finally:
        conn.close()


def get_snapshots(riot_id: str, limit: int = 20) -> list:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, created_at, tilt_score, tilt_level, matches_analyzed "
            "FROM tilt_snapshots WHERE riot_id = ? ORDER BY id DESC LIMIT ?",
            (riot_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def save_session(riot_id: str):
    """Record that a coach exchange happened — deliberately without its text.

    Rows here are keyed by the *searched* Riot ID, which is not the person
    typing: anyone can look up anyone. Storing the conversation under that key
    filed one visitor's words under a stranger's gamertag and let the next
    visitor read them back. Only the count and timestamp are kept now; the
    conversation itself lives in the browser that is having it.
    """
    conn = get_conn()
    try:
        with conn:
            conn.execute("INSERT INTO coach_sessions (riot_id) VALUES (?)", (riot_id,))
    finally:
        conn.close()


def get_sessions(riot_id: str, limit: int = 20) -> list:
    """Session metadata only. The text columns are never selected — see save_session."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, created_at FROM coach_sessions "
            "WHERE riot_id = ? ORDER BY id DESC LIMIT ?",
            (riot_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# --- Analytics ---------------------------------------------------------------

FUNNEL_STEPS = [
    ("searched", "player_search"),
    ("analyzed", "analyze_run"),
    ("tilt_checked", "tilt_check"),
    ("coached", "coach_message_sent"),
]

LATENCY_EVENTS = ("analyze_run", "tilt_check", "coach_message_sent")


# Analytics ingestion is unauthenticated by design (the browser posts to it), so
# the table is the one thing on this box an anonymous caller can grow without
# limit. At the current 120 req/min per IP, 25 events of ~1 KB each, that is
# ~180 MB/hour from a single address onto a 20 GB disk — and a full disk takes
# the whole app down, not just analytics. Two independent bounds:
ANALYTICS_RETENTION_DAYS = int(os.getenv("ANALYTICS_RETENTION_DAYS", "90"))
ANALYTICS_MAX_ROWS = int(os.getenv("ANALYTICS_MAX_ROWS", "500000"))
_PRUNE_EVERY = 200  # batches between prune passes; cheap amortised cost
_insert_count = 0


def _prune_analytics(conn) -> None:
    """Drop events past the retention window, then enforce a hard row ceiling.

    The ceiling is the part that matters under abuse: a flood can blow past
    500k rows well inside the retention window, so age alone is not a bound.
    """
    conn.execute(
        "DELETE FROM analytics_events WHERE created_at < datetime('now', ?)",
        (f"-{ANALYTICS_RETENTION_DAYS} days",),
    )
    conn.execute(
        "DELETE FROM analytics_events WHERE id <= "
        "(SELECT MAX(id) - ? FROM analytics_events)",
        (ANALYTICS_MAX_ROWS,),
    )


def insert_events(visitor_id: str, session_id: str, events: list):
    """Insert a batch of client events in a single transaction.

    Each event is a dict with keys: name, ts (client ms epoch), path, props.
    Server-received time is recorded by the created_at column default.
    """
    global _insert_count
    conn = get_conn()
    try:
        with conn:
            conn.executemany(
                "INSERT INTO analytics_events (visitor_id, session_id, name, path, props_json, client_ts) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        visitor_id,
                        session_id,
                        e["name"],
                        e.get("path"),
                        json.dumps(e.get("props") or {}),
                        e.get("ts"),
                    )
                    for e in events
                ],
            )
            _insert_count += 1
            if _insert_count % _PRUNE_EVERY == 0:
                _prune_analytics(conn)
    finally:
        conn.close()


def _percentile(sorted_values: list, pct: float):
    """Nearest-rank percentile over an already-sorted list. None when empty."""
    if not sorted_values:
        return None
    rank = max(0, math.ceil(pct / 100 * len(sorted_values)) - 1)
    return sorted_values[rank]


def get_analytics_summary() -> dict:
    conn = get_conn()
    try:
        totals = dict(conn.execute(
            "SELECT COUNT(*) AS events, COUNT(DISTINCT visitor_id) AS visitors, "
            "COUNT(DISTINCT session_id) AS sessions, "
            "MIN(created_at) AS first_event, MAX(created_at) AS last_event "
            "FROM analytics_events"
        ).fetchone())
        daily = [dict(row) for row in conn.execute(
            "SELECT date(created_at) AS date, COUNT(*) AS events, "
            "COUNT(DISTINCT visitor_id) AS visitors, COUNT(DISTINCT session_id) AS sessions "
            "FROM analytics_events WHERE date(created_at) >= date('now', '-13 days') "
            "GROUP BY date(created_at) ORDER BY date"
        ).fetchall()]
        by_event = [dict(row) for row in conn.execute(
            "SELECT name, COUNT(*) AS count FROM analytics_events "
            "GROUP BY name ORDER BY count DESC"
        ).fetchall()]
        funnel = {
            step: conn.execute(
                "SELECT COUNT(DISTINCT visitor_id) FROM analytics_events WHERE name = ?",
                (event_name,),
            ).fetchone()[0]
            for step, event_name in FUNNEL_STEPS
        }
        # Percentiles in Python from fetched latencies — fine at this scale
        # (see ANALYTICS.md for the tradeoff vs SQL window functions).
        latency_ms = {}
        for event_name in LATENCY_EVENTS:
            rows = conn.execute(
                "SELECT CAST(json_extract(props_json, '$.latency_ms') AS REAL) AS ms "
                "FROM analytics_events "
                "WHERE name = ? AND json_extract(props_json, '$.latency_ms') IS NOT NULL",
                (event_name,),
            ).fetchall()
            values = sorted(row["ms"] for row in rows)
            latency_ms[event_name] = {
                "p50": _percentile(values, 50),
                "p95": _percentile(values, 95),
            }
        errors = [dict(row) for row in conn.execute(
            "SELECT json_extract(props_json, '$.endpoint') AS endpoint, "
            "json_extract(props_json, '$.status') AS status, COUNT(*) AS count "
            "FROM analytics_events WHERE name = 'api_error' "
            "GROUP BY endpoint, status ORDER BY count DESC"
        ).fetchall()]
        return {
            "totals": totals,
            "daily": daily,
            "by_event": by_event,
            "funnel": funnel,
            "latency_ms": latency_ms,
            "errors": errors,
        }
    finally:
        conn.close()
