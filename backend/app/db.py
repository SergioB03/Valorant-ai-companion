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


def save_session(riot_id: str, user_message: str, coach_reply: str):
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                "INSERT INTO coach_sessions (riot_id, user_message, coach_reply) VALUES (?, ?, ?)",
                (riot_id, user_message, coach_reply),
            )
    finally:
        conn.close()


def get_sessions(riot_id: str, limit: int = 20) -> list:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, created_at, user_message, coach_reply "
            "FROM coach_sessions WHERE riot_id = ? ORDER BY id DESC LIMIT ?",
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


def insert_events(visitor_id: str, session_id: str, events: list):
    """Insert a batch of client events in a single transaction.

    Each event is a dict with keys: name, ts (client ms epoch), path, props.
    Server-received time is recorded by the created_at column default.
    """
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
