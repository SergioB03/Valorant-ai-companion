"""The counters that guard money and abuse.

A regression here is expensive rather than merely broken, so these pin the
behaviour that matters: increments are not lost, the ceiling is enforced, and
an unreadable counter refuses the call rather than guessing.
"""

import pytest

from app import budget, budget_store


@pytest.fixture(autouse=True)
def _fresh_store(monkeypatch, tmp_path):
    """Each test gets its own SQLite file and a fresh store singleton."""
    monkeypatch.setenv("VAC_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("BUDGET_TABLE_NAME", raising=False)
    budget_store.reset_store_for_tests()

    import app.db

    app.db._STATE_DIR = tmp_path
    app.db.DB_PATH = tmp_path / "companion.sqlite3"
    app.db._initialized = False
    yield
    budget_store.reset_store_for_tests()


class TestBackendSelection:
    def test_sqlite_by_default(self):
        assert budget_store.get_store().name == "sqlite"

    def test_dynamo_when_table_is_named(self, monkeypatch):
        """Set BUDGET_TABLE_NAME and the counters move off the instance."""
        monkeypatch.setenv("BUDGET_TABLE_NAME", "rebuy-quotas")
        budget_store.reset_store_for_tests()
        created = {}

        class FakeTable:
            pass

        def fake_resource(*a, **kw):
            created["region"] = kw.get("region_name")

            class R:
                def Table(self, name):
                    created["table"] = name
                    return FakeTable()

            return R()

        import boto3

        monkeypatch.setattr(boto3, "resource", fake_resource)
        store = budget_store.get_store()
        assert store.name == "dynamodb"
        assert created["table"] == "rebuy-quotas"


class TestSpendAccounting:
    def test_spend_accumulates(self):
        assert budget.spent_today() == 0.0
        budget.record_spend("claude-sonnet-5", 1_000_000, 0)  # $3.00
        assert budget.spent_today() == pytest.approx(3.0)
        budget.record_spend("claude-sonnet-5", 1_000_000, 0)
        assert budget.spent_today() == pytest.approx(6.0)

    def test_unknown_model_priced_at_the_dearest_rate(self):
        """A typo in CLAUDE_MODEL must never make the breaker under-count."""
        unknown = budget.estimate_cost_usd("claude-typo-9", 1_000_000, 0)
        dearest = budget.estimate_cost_usd("claude-fable-5", 1_000_000, 0)
        assert unknown == dearest


class TestBreaker:
    def test_allows_calls_under_the_ceiling(self, monkeypatch):
        monkeypatch.setenv("DAILY_BUDGET_USD", "5.00")
        budget.check_budget()  # must not raise

    def test_blocks_everyone_once_the_ceiling_is_reached(self, monkeypatch):
        monkeypatch.setenv("DAILY_BUDGET_USD", "5.00")
        budget.record_spend("claude-sonnet-5", 0, 400_000)  # $6.00
        with pytest.raises(budget.BudgetExceeded):
            budget.check_budget()

    def test_zero_disables_the_breaker(self, monkeypatch):
        monkeypatch.setenv("DAILY_BUDGET_USD", "0")
        budget.record_spend("claude-fable-5", 0, 1_000_000)
        budget.check_budget()  # disabled, so no raise

    def test_unreadable_counter_fails_closed(self, monkeypatch):
        """Cannot prove we are under budget => refuse. A 503 is recoverable;
        an unbounded bill is not."""
        monkeypatch.setenv("DAILY_BUDGET_USD", "5.00")

        def explode(_day):
            raise RuntimeError("dynamodb unreachable")

        monkeypatch.setattr(budget_store.get_store(), "spent_today", explode)
        with pytest.raises(budget.BudgetExceeded):
            budget.check_budget()

    def test_a_failed_write_does_not_break_the_response(self, monkeypatch):
        """The call already happened; raising would fail a served request."""

        def explode(_day, _cost):
            raise RuntimeError("write failed")

        monkeypatch.setattr(budget_store.get_store(), "add_spend", explode)
        assert budget.record_spend("claude-sonnet-5", 1000, 500) > 0


class TestPerSourceQuota:
    def test_blocks_after_the_allowance_is_used(self, monkeypatch):
        monkeypatch.setenv("FREE_AI_ACTIONS_PER_IP_PER_DAY", "3")
        for _ in range(3):
            budget.check_ip_quota("203.0.113.7")
            budget.record_ip_use("203.0.113.7")
        with pytest.raises(budget.QuotaExceeded):
            budget.check_ip_quota("203.0.113.7")

    def test_one_heavy_source_does_not_block_others(self, monkeypatch):
        monkeypatch.setenv("FREE_AI_ACTIONS_PER_IP_PER_DAY", "3")
        for _ in range(3):
            budget.record_ip_use("203.0.113.7")
        with pytest.raises(budget.QuotaExceeded):
            budget.check_ip_quota("203.0.113.7")
        budget.check_ip_quota("198.51.100.4")  # unaffected

    def test_addresses_are_never_stored(self):
        """ANALYTICS.md promises no IPs on disk; this must not reintroduce them."""
        ip = "203.0.113.42"
        budget.record_ip_use(ip)
        from app.db import get_conn

        conn = get_conn()
        try:
            keys = [r["ip_key"] for r in conn.execute("SELECT ip_key FROM ip_usage")]
        finally:
            conn.close()
        assert keys
        assert all(ip not in k for k in keys)

    def test_unreadable_counter_fails_closed(self, monkeypatch):
        monkeypatch.setenv("FREE_AI_ACTIONS_PER_IP_PER_DAY", "40")

        def explode(_day, _key):
            raise RuntimeError("unreachable")

        monkeypatch.setattr(budget_store.get_store(), "ip_calls", explode)
        with pytest.raises(budget.QuotaExceeded):
            budget.check_ip_quota("203.0.113.7")
