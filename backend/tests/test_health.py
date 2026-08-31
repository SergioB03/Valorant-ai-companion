"""Health endpoints and the HenrikDev key migration."""

import importlib
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestLiveness:
    def test_health_is_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_health_needs_no_configuration(self, client, monkeypatch):
        """A load balancer restarts the container when this fails, so it must
        not depend on keys or upstreams -- otherwise their outage becomes our
        restart loop."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("HENRIK_API_KEY", raising=False)
        monkeypatch.delenv("RIOT_API_KEY", raising=False)
        assert client.get("/health").status_code == 200


class TestReadiness:
    def test_ready_when_keys_present(self, client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("HENRIK_API_KEY", "HDEV-test")
        r = client.get("/health/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ready"

    def test_degraded_503_when_a_key_is_missing(self, client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("HENRIK_API_KEY", "HDEV-test")
        r = client.get("/health/ready")
        assert r.status_code == 503
        assert r.json()["checks"]["claude_configured"] is False

    def test_legacy_key_name_still_counts_as_configured(self, client, monkeypatch):
        """Production still serves /vac/RIOT_API_KEY from SSM during the rename."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("HENRIK_API_KEY", raising=False)
        monkeypatch.setenv("RIOT_API_KEY", "HDEV-legacy")
        r = client.get("/health/ready")
        assert r.json()["checks"]["match_provider_configured"] is True

    def test_rag_absence_does_not_make_us_unready(self, client, monkeypatch):
        """RAG is optional: without it /meta degrades, the service does not."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("HENRIK_API_KEY", "HDEV-test")
        assert client.get("/health/ready").status_code == 200


class TestKeyMigration:
    """
    infra/deploy.sh writes every /vac/* SSM parameter into backend/.env, so the
    code must keep reading the old name until that parameter is renamed --
    otherwise the next deploy takes the app down.
    """

    @staticmethod
    def _reload_with(env: dict):
        from app.services import riot_service

        for k in ("HENRIK_API_KEY", "RIOT_API_KEY"):
            os.environ.pop(k, None)
        os.environ.update(env)
        importlib.reload(riot_service)
        return riot_service.HENRIK_API_KEY

    def test_new_name_is_used(self):
        assert self._reload_with({"HENRIK_API_KEY": "new"}) == "new"

    def test_legacy_name_still_works(self):
        assert self._reload_with({"RIOT_API_KEY": "legacy"}) == "legacy"

    def test_new_name_wins_when_both_are_set(self):
        assert self._reload_with({"HENRIK_API_KEY": "new", "RIOT_API_KEY": "old"}) == "new"

    def teardown_method(self):
        """Restore the suite-wide value so later tests are unaffected."""
        self._reload_with({"HENRIK_API_KEY": "HDEV-test-not-a-real-key"})
