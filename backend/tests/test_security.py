"""Security-behaviour tests.

These cover the parts where a regression is silent: a rate-limit key that stops
identifying the caller, an admin gate that starts accepting nothing, or response
headers that quietly disappear. All of them fail open rather than loudly, so
they are exactly the things worth pinning down in tests.
"""

import os
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.limiter import client_ip
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _request(headers: dict | None = None, peer: str = "10.0.0.1"):
    request = Mock()
    request.headers = headers or {}
    request.client = Mock(host=peer)
    return request


class TestRateLimitKey:
    """
    The limit key decides who shares a quota. Behind CloudFront the TCP peer is
    always a proxy, so keying on it would put every visitor in one bucket and
    make the limits meaningless.
    """

    def test_cloudfront_viewer_address_wins_over_the_socket(self):
        req = _request({"cloudfront-viewer-address": "203.0.113.7:53124"})
        assert client_ip(req) == "203.0.113.7"

    def test_ipv6_is_bucketed_by_64(self):
        """One IPv6 allocation hands out /64s freely; keying the full address
        would let a single machine mint unlimited quota keys."""
        req = _request({"cloudfront-viewer-address": "[2001:db8::1]:443"})
        assert client_ip(req) == "2001:db8::/64"

        other_in_same_64 = _request({"cloudfront-viewer-address": "[2001:db8::99ff]:443"})
        assert client_ip(other_in_same_64) == client_ip(req)

    def test_garbage_header_falls_back_to_the_socket(self):
        req = _request({"cloudfront-viewer-address": "not-an-ip"}, peer="10.0.0.5")
        assert client_ip(req) == "10.0.0.5"

    def test_absent_header_falls_back_to_the_socket(self):
        assert client_ip(_request(peer="10.0.0.9")) == "10.0.0.9"


class TestAdminGate:
    """/analytics/summary exposes usage and spend; /meta/reindex burns CPU."""

    def test_missing_token_is_refused(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "correct-horse")
        assert client.get("/analytics/summary").status_code == 403

    def test_wrong_token_is_refused(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "correct-horse")
        r = client.get("/analytics/summary", headers={"X-Admin-Token": "guess"})
        assert r.status_code == 403

    def test_unset_admin_token_disables_the_route_entirely(self, client, monkeypatch):
        """Fail closed: an unset token must not mean 'no auth required'."""
        monkeypatch.delenv("ADMIN_TOKEN", raising=False)
        assert client.get("/analytics/summary").status_code == 403
        r = client.get("/analytics/summary", headers={"X-Admin-Token": ""})
        assert r.status_code == 403


class TestSecurityHeaders:
    def test_present_on_every_response(self, client):
        h = client.get("/").headers
        assert h["X-Content-Type-Options"] == "nosniff"
        assert h["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
        assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_hsts_only_in_production(self, client):
        """Sending HSTS from an HTTP dev server would pin localhost to https."""
        assert "Strict-Transport-Security" not in client.get("/").headers


class TestCors:
    def test_credentials_are_not_enabled(self, client):
        """Nothing uses cookies; credentialed CORS would only add risk."""
        r = client.get("/", headers={"Origin": "https://rebuy.gg"})
        assert r.headers.get("Access-Control-Allow-Credentials") != "true"

    def test_unlisted_origin_is_not_echoed_back(self, client):
        r = client.get("/", headers={"Origin": "https://evil.example.com"})
        assert r.headers.get("Access-Control-Allow-Origin") != "https://evil.example.com"

    def test_wildcard_origin_refused_outside_development(self):
        """
        Starlette echoes the caller's origin rather than sending a literal '*',
        so a wildcard is not the harmless catch-all it appears to be.
        """
        assert os.getenv("CORS_ORIGINS") != "*"
