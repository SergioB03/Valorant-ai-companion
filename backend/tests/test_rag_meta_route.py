"""/meta routes: warm-up readiness gate and response passthrough.

The core property under test: the request path must NEVER rebuild the index.
A missing/corrupt collection on the live box used to make a random visitor's
/meta/ask trigger a full corpus re-embed inline (multi-second, under the
module lock, inside the proxy's 60s window) — now it answers 503 +
Retry-After, which the frontend renders as a graceful warming notice.
"""

import pytest
from app.deps import ai_quota
from app.main import app
from app.services import rag_service
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    # ai_quota charges the caller's daily AI allowance in SQLite; these tests
    # are about routing, not quotas, so it is overridden wholesale.
    app.dependency_overrides[ai_quota] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(ai_quota, None)


CANNED = {
    "answer": "A Phantom costs 2,900 credits.",
    "sources": [
        {"source": "economy.md", "section": "Weapon prices (approximate)",
         "snippet": "Rifles: ...", "used": True},
    ],
    "corpus_vintage": "notes current to patch 13.05 (2026-09-01)",
}


class TestAskReadinessGate:
    def test_warming_index_returns_503_with_retry_after(self, client, monkeypatch):
        monkeypatch.setattr(rag_service, "is_ready", lambda: False)
        r = client.post("/meta/ask", json={"question": "How much is a Phantom?"})
        assert r.status_code == 503
        assert r.headers.get("Retry-After") == "15"
        assert "warming up" in r.json()["detail"]

    def test_request_path_never_rebuilds_the_index(self, client, monkeypatch):
        def boom():
            raise AssertionError("ensure_index() must not run on the request path")

        monkeypatch.setattr(rag_service, "ensure_index", boom)
        monkeypatch.setattr(rag_service, "is_ready", lambda: True)
        monkeypatch.setattr(rag_service, "ask_meta", lambda q: CANNED)
        r = client.post("/meta/ask", json={"question": "How much is a Phantom?"})
        assert r.status_code == 200

    def test_ready_path_passes_the_contract_fields_through(self, client, monkeypatch):
        monkeypatch.setattr(rag_service, "is_ready", lambda: True)
        monkeypatch.setattr(rag_service, "ask_meta", lambda q: CANNED)
        body = client.post("/meta/ask", json={"question": "How much is a Phantom?"}).json()
        assert body["answer"].startswith("A Phantom")
        assert body["sources"][0]["used"] is True
        assert body["corpus_vintage"] == "notes current to patch 13.05 (2026-09-01)"

    def test_blank_question_is_rejected_before_any_work(self, client, monkeypatch):
        monkeypatch.setattr(rag_service, "is_ready", lambda: True)
        r = client.post("/meta/ask", json={"question": "   "})
        assert r.status_code == 400


class TestStatus:
    def test_status_reports_corpus_vintage(self, client, monkeypatch):
        monkeypatch.setattr(
            rag_service,
            "status",
            lambda: {"ready": True, "documents": 11, "chunks": 82,
                     "corpus_vintage": "notes current to patch 13.05 (2026-09-01)"},
        )
        body = client.get("/meta/status").json()
        assert body["available"] is True
        assert body["corpus_vintage"] == "notes current to patch 13.05 (2026-09-01)"


class TestIsReady:
    def test_false_while_another_thread_holds_the_index_lock(self, monkeypatch):
        """While the warm thread (or a reindex) holds the lock, readiness must
        answer immediately instead of queueing behind a multi-second embed."""
        monkeypatch.setattr(rag_service, "_ready", False)
        import threading

        acquired = threading.Event()
        release = threading.Event()

        def hold():
            with rag_service._lock:
                acquired.set()
                release.wait(timeout=5)

        t = threading.Thread(target=hold, daemon=True)
        t.start()
        try:
            assert acquired.wait(timeout=5)
            assert rag_service.is_ready() is False
        finally:
            release.set()
            t.join(timeout=5)

    def test_true_once_collection_reports_chunks(self, monkeypatch):
        class FakeCollection:
            def count(self):
                return 82

        monkeypatch.setattr(rag_service, "_ready", False)
        monkeypatch.setattr(rag_service, "_get_collection", lambda: FakeCollection())
        assert rag_service.is_ready() is True
        # And the result is latched — no per-request collection poke afterwards.
        monkeypatch.setattr(
            rag_service, "_get_collection",
            lambda: (_ for _ in ()).throw(AssertionError("should be latched")),
        )
        assert rag_service.is_ready() is True

    def test_empty_collection_is_not_ready(self, monkeypatch):
        class FakeCollection:
            def count(self):
                return 0

        monkeypatch.setattr(rag_service, "_ready", False)
        monkeypatch.setattr(rag_service, "_get_collection", lambda: FakeCollection())
        assert rag_service.is_ready() is False
