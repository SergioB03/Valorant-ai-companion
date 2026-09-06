"""The quota-header interface the frontend keys its friendly 429 state on.

Contract (docs/GROWTH-FEATURES.md item 7 + the Wave 2/3 implementation
contract): the daily-allowance 429 carries ``X-Quota-Exhausted: 1`` (the ONLY
signal for the "out of free AI actions" copy — three different 429s exist),
``Retry-After`` with the seconds to UTC midnight, and ``X-Quota-Limit``;
successful AI responses carry ``X-Quota-Limit`` too so the caption never
hardcodes the env-configurable number; all three are CORS-exposed; and every
AI-spending response is ``Cache-Control: no-store`` so CloudFront/browsers can
never serve one caller's answer or quota headers to another.
"""

import pytest
from fastapi.testclient import TestClient

import app.deps as deps
from app.budget import QuotaExceeded
from app.main import app
from app.services import rag_service

CANNED_ANSWER = {"answer": "canned", "sources": [], "corpus_vintage": "test"}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def quota_available(monkeypatch):
    """Real ai_quota dependency, but no SQLite bookkeeping and a known limit."""
    monkeypatch.setattr(deps, "check_ip_quota", lambda ip: None)
    monkeypatch.setattr(deps, "record_ip_use", lambda ip: None)
    monkeypatch.setattr(deps, "daily_ip_quota", lambda: 40)


@pytest.fixture
def quota_exhausted(monkeypatch):
    def refuse(ip):
        raise QuotaExceeded("daily limit reached")

    monkeypatch.setattr(deps, "check_ip_quota", refuse)
    monkeypatch.setattr(deps, "daily_ip_quota", lambda: 40)


@pytest.fixture
def rag_ready(monkeypatch):
    monkeypatch.setattr(rag_service, "is_available", lambda: True)
    monkeypatch.setattr(rag_service, "is_ready", lambda: True)
    monkeypatch.setattr(rag_service, "ask_meta", lambda q: CANNED_ANSWER)


class TestSuccessfulResponses:
    def test_success_carries_the_quota_limit(self, client, quota_available, rag_ready):
        r = client.post("/meta/ask", json={"question": "What changed for Cypher?"})
        assert r.status_code == 200
        assert r.headers["X-Quota-Limit"] == "40"

    def test_success_is_never_cacheable(self, client, quota_available, rag_ready):
        r = client.post("/meta/ask", json={"question": "What changed for Omen?"})
        assert r.headers["Cache-Control"] == "no-store"

    def test_limit_header_tracks_the_env_not_a_constant(
        self, client, rag_ready, monkeypatch
    ):
        """The frontend caption reads this header precisely so 40 is never
        hardcoded anywhere — the header must follow the configuration."""
        monkeypatch.setattr(deps, "check_ip_quota", lambda ip: None)
        monkeypatch.setattr(deps, "record_ip_use", lambda ip: None)
        monkeypatch.setenv("FREE_AI_ACTIONS_PER_IP_PER_DAY", "7")
        r = client.post("/meta/ask", json={"question": "What about Sage?"})
        assert r.headers["X-Quota-Limit"] == "7"


class TestExhausted429:
    def test_daily_quota_429_carries_the_full_interface(
        self, client, quota_exhausted
    ):
        r = client.post("/meta/ask", json={"question": "What changed for KAYO?"})
        assert r.status_code == 429
        assert r.headers["X-Quota-Exhausted"] == "1"
        assert r.headers["X-Quota-Limit"] == "40"
        # Seconds to UTC midnight: always in (0, 24h].
        assert 1 <= int(r.headers["Retry-After"]) <= 86400
        # The 429 is per-caller too — it must not be cached either.
        assert r.headers["Cache-Control"] == "no-store"

    def test_every_ai_spending_endpoint_shares_the_429_interface(
        self, client, quota_exhausted
    ):
        """The dependency runs before any handler code, so none of these
        touch HenrikDev or Claude."""
        responses = [
            client.get("/claude/analyze/Some/Player"),
            client.get("/mental/tilt-check/Some/Player"),
            client.post(
                "/mental/coach",
                json={"game_name": "Some", "tag_line": "Player", "message": "hi"},
            ),
        ]
        for r in responses:
            assert r.status_code == 429
            assert r.headers["X-Quota-Exhausted"] == "1"
            assert r.headers["X-Quota-Limit"] == "40"
            assert "Retry-After" in r.headers
            assert r.headers["Cache-Control"] == "no-store"


class TestScoping:
    def test_non_ai_routes_are_not_marked_no_store(self, client):
        """Only the money-spending endpoints get the header; static-ish JSON
        like the root or health must stay cacheable-by-default."""
        assert "Cache-Control" not in client.get("/").headers
        assert "Cache-Control" not in client.get("/health").headers

    def test_cors_exposes_the_quota_headers(self, client):
        """Without expose_headers, cross-origin JS cannot read the interface
        at all — the frontend would silently never show the friendly state."""
        r = client.get("/", headers={"Origin": "https://rebuy.gg"})
        exposed = r.headers.get("Access-Control-Expose-Headers", "")
        exposed_names = {h.strip().lower() for h in exposed.split(",")}
        assert {"x-quota-exhausted", "x-quota-limit", "retry-after"} <= exposed_names


class TestRetryAfterClock:
    def test_seconds_to_utc_midnight_is_bounded(self):
        assert 1 <= deps.seconds_to_utc_midnight() <= 86400
