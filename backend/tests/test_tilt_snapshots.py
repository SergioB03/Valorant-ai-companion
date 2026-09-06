"""Bounds on tilt_snapshots — the Wave-3 ritual precondition.

The returning-player ritual deliberately multiplies writes to this table, and
the table holds derived data about *searched* players (anyone can look up
anyone), which is the project's largest open Riot-policy exposure. Three
bounds are pinned here: full reports are never persisted (and old ones are
scrubbed), no player accumulates more than the per-player cap, and rows age
out on the analytics-pruning cadence.
"""

import pytest

from app import db


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch, tmp_path):
    """Each test gets its own SQLite file (same pattern as test_budget_store)."""
    monkeypatch.setattr(db, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "companion.sqlite3")
    monkeypatch.setattr(db, "_initialized", False)


def _report(score: int = 50) -> dict:
    return {
        "tilt_score": score,
        "tilt_level": "heated",
        "matches_analyzed": 10,
        "signals": ["loss_streak"],
        "per_map": {"Ascent": {"losses": 3}},
    }


def _rows(query: str, params: tuple = ()):
    conn = db.get_conn()
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


class TestReportJson:
    def test_report_json_is_never_written(self):
        db.save_snapshot("player#one", _report())
        rows = _rows("SELECT report_json FROM tilt_snapshots")
        assert len(rows) == 1
        assert rows[0]["report_json"] is None

    def test_scalar_columns_still_land(self):
        db.save_snapshot("player#one", _report(score=72))
        [row] = _rows(
            "SELECT tilt_score, tilt_level, matches_analyzed FROM tilt_snapshots"
        )
        assert (row["tilt_score"], row["tilt_level"], row["matches_analyzed"]) == (
            72, "heated", 10,
        )

    def test_migration_scrubs_blobs_an_old_database_still_holds(self, monkeypatch):
        # Write a legacy-shaped row the way the old code did...
        conn = db.get_conn()
        with conn:
            conn.execute(
                "INSERT INTO tilt_snapshots (riot_id, tilt_score, tilt_level, "
                "matches_analyzed, report_json) VALUES (?, ?, ?, ?, ?)",
                ("player#old", 60, "heated", 10, '{"whole": "report"}'),
            )
        conn.close()
        # ...then boot "a new process" against the same file: MIGRATIONS run.
        monkeypatch.setattr(db, "_initialized", False)
        rows = _rows("SELECT report_json FROM tilt_snapshots")
        assert rows and all(r["report_json"] is None for r in rows)


class TestPerPlayerCap:
    def test_inserts_past_the_cap_prune_the_same_players_oldest(self, monkeypatch):
        monkeypatch.setattr(db, "TILT_SNAPSHOTS_PER_PLAYER", 5)
        for i in range(8):
            db.save_snapshot("player#capped", _report(score=i))
        rows = _rows(
            "SELECT tilt_score FROM tilt_snapshots WHERE riot_id = ? ORDER BY id",
            ("player#capped",),
        )
        # Exactly the cap survives, and it is the NEWEST five (scores 3..7).
        assert [r["tilt_score"] for r in rows] == [3, 4, 5, 6, 7]

    def test_one_players_flood_never_touches_another_players_history(
        self, monkeypatch
    ):
        monkeypatch.setattr(db, "TILT_SNAPSHOTS_PER_PLAYER", 3)
        db.save_snapshot("player#quiet", _report(score=11))
        for i in range(10):
            db.save_snapshot("player#noisy", _report(score=i))
        quiet = _rows(
            "SELECT tilt_score FROM tilt_snapshots WHERE riot_id = ?",
            ("player#quiet",),
        )
        assert [r["tilt_score"] for r in quiet] == [11]
        noisy = _rows(
            "SELECT COUNT(*) AS n FROM tilt_snapshots WHERE riot_id = ?",
            ("player#noisy",),
        )
        assert noisy[0]["n"] == 3

    def test_default_cap_is_30(self):
        assert db.TILT_SNAPSHOTS_PER_PLAYER == 30


class TestRetentionSweep:
    @staticmethod
    def _insert_aged(riot_id: str, created_at: str):
        conn = db.get_conn()
        with conn:
            conn.execute(
                "INSERT INTO tilt_snapshots (riot_id, created_at, tilt_score, "
                "tilt_level, matches_analyzed) VALUES (?, ?, ?, ?, ?)",
                (riot_id, created_at, 50, "heated", 10),
            )
        conn.close()

    def test_sweep_drops_only_rows_past_the_window(self):
        self._insert_aged("player#stale", "2020-01-01 00:00:00")
        db.save_snapshot("player#fresh", _report())
        conn = db.get_conn()
        try:
            with conn:
                db._prune_analytics(conn)
        finally:
            conn.close()
        rows = _rows("SELECT riot_id FROM tilt_snapshots")
        assert [r["riot_id"] for r in rows] == ["player#fresh"]

    def test_sweep_rides_the_analytics_ingest_cadence(self, monkeypatch):
        """No timer exists for this — it MUST fire from insert_events, or the
        retention promise silently becomes dead code."""
        monkeypatch.setattr(db, "_PRUNE_EVERY", 1)
        monkeypatch.setattr(db, "_insert_count", 0)
        self._insert_aged("player#stale", "2020-01-01 00:00:00")
        db.insert_events(
            "visitor", "session",
            [{"name": "page_view", "ts": 0, "path": "/", "props": {}}],
        )
        assert _rows("SELECT * FROM tilt_snapshots") == []
