"""The HenrikDev TTL cache in riot_service (IN4).

The cache exists because /claude/analyze, /mental/tilt-check and /mental/coach
each fetch the same match history for one player touring the tabs — 3-4
identical upstream calls against a 30 req/min key. These tests pin the cache's
contract: identical requests hit upstream once inside the TTL, any param
variance is a separate entry, expiry refetches, errors are never cached, and
the entry count stays bounded.

No network: httpx.AsyncClient is replaced with a counting fake.
"""

import asyncio

import httpx
import pytest

from app.services import riot_service


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}", request=None, response=None
            )


class FakeClient:
    """Stands in for httpx.AsyncClient; records every GET it serves."""

    calls: list = []          # (url, params) per upstream hit
    responses: list = []      # queue of FakeResponse/Exception; last one repeats

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None, params=None):
        FakeClient.calls.append((url, dict(params or {})))
        item = (
            FakeClient.responses.pop(0)
            if len(FakeClient.responses) > 1
            else FakeClient.responses[0]
        )
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def clean_cache(monkeypatch):
    monkeypatch.setattr(riot_service.httpx, "AsyncClient", FakeClient)
    riot_service._CACHE.clear()
    FakeClient.calls = []
    FakeClient.responses = [FakeResponse({"data": {"name": "Player"}})]
    yield
    riot_service._CACHE.clear()


def test_account_lookup_served_from_cache():
    asyncio.run(riot_service.get_account_by_riot_id("Player", "TAG"))
    asyncio.run(riot_service.get_account_by_riot_id("Player", "TAG"))
    assert len(FakeClient.calls) == 1


def test_match_history_served_from_cache_and_payload_identical():
    payload = {"data": [{"metadata": {"matchid": "m1"}}]}
    FakeClient.responses = [FakeResponse(payload)]
    first = asyncio.run(riot_service.get_match_history("Player", "TAG", size=10))
    second = asyncio.run(riot_service.get_match_history("Player", "TAG", size=10))
    assert first == second == payload
    assert len(FakeClient.calls) == 1


def test_param_variance_bypasses_cache():
    """size/mode/region variance must be a different key, never a wrong-shape hit."""
    asyncio.run(riot_service.get_match_history("Player", "TAG", size=10))
    asyncio.run(riot_service.get_match_history("Player", "TAG", size=5))
    asyncio.run(riot_service.get_match_history("Player", "TAG", size=10, mode="competitive"))
    asyncio.run(riot_service.get_match_history("Player", "TAG", region="eu", size=10))
    assert len(FakeClient.calls) == 4
    # ...and each repeated exactly is still one upstream call total.
    asyncio.run(riot_service.get_match_history("Player", "TAG", size=10))
    assert len(FakeClient.calls) == 4


def test_expiry_refetches(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(riot_service.time, "monotonic", lambda: clock["now"])

    asyncio.run(riot_service.get_match_history("Player", "TAG", size=10))
    clock["now"] += riot_service.MATCHES_TTL - 1
    asyncio.run(riot_service.get_match_history("Player", "TAG", size=10))
    assert len(FakeClient.calls) == 1  # still fresh

    clock["now"] += 2  # now past the TTL
    asyncio.run(riot_service.get_match_history("Player", "TAG", size=10))
    assert len(FakeClient.calls) == 2


def test_account_ttl_longer_than_matches_ttl(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(riot_service.time, "monotonic", lambda: clock["now"])

    asyncio.run(riot_service.get_account_by_riot_id("Player", "TAG"))
    clock["now"] += riot_service.MATCHES_TTL + 1  # past matches TTL, inside account TTL
    asyncio.run(riot_service.get_account_by_riot_id("Player", "TAG"))
    assert len(FakeClient.calls) == 1

    clock["now"] += riot_service.ACCOUNT_TTL
    asyncio.run(riot_service.get_account_by_riot_id("Player", "TAG"))
    assert len(FakeClient.calls) == 2


def test_errors_are_not_cached():
    FakeClient.responses = [
        FakeResponse({"errors": ["not found"]}, status_code=404),
        FakeResponse({"data": {"name": "Player"}}),
    ]
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(riot_service.get_account_by_riot_id("Player", "TAG"))
    # The failure must not poison the cache: the retry goes upstream and succeeds.
    result = asyncio.run(riot_service.get_account_by_riot_id("Player", "TAG"))
    assert result == {"data": {"name": "Player"}}
    assert len(FakeClient.calls) == 2


def test_cache_entry_count_is_capped():
    for i in range(riot_service._CACHE_MAX + 50):
        asyncio.run(riot_service.get_match_history(f"Player{i}", "TAG", size=10))
    assert len(riot_service._CACHE) <= riot_service._CACHE_MAX
    # Oldest entries were evicted; the newest survives.
    newest_key = (
        f"{riot_service.HENRIK_BASE_URL}/v3/matches/na/Player"
        f"{riot_service._CACHE_MAX + 49}/TAG",
        (("size", 10),),
    )
    assert newest_key in riot_service._CACHE


def test_eviction_prefers_expired_entries(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(riot_service.time, "monotonic", lambda: clock["now"])

    # Fill the cache; the first half then expires.
    for i in range(riot_service._CACHE_MAX):
        riot_service._cache_put((f"k{i}",), {"i": i}, ttl=60 if i < 128 else 600)
    clock["now"] += 120

    riot_service._cache_put(("fresh",), {"fresh": True}, ttl=600)
    assert ("fresh",) in riot_service._CACHE
    # The expired half is gone; the long-TTL half survived the eviction pass.
    assert ("k0",) not in riot_service._CACHE
    assert ("k200",) in riot_service._CACHE
    assert len(riot_service._CACHE) <= riot_service._CACHE_MAX
