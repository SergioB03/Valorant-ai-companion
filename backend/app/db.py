import json
import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "companion.sqlite3"

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
