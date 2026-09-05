"""ask_meta behaviour: used-source flags, parse fallback, two-tier floor,
answer cache, and corpus vintage — all with retrieval and Claude stubbed
(zero chroma, zero network, zero spend)."""

import json
from types import SimpleNamespace

import pytest
from app import db
from app.services import claude_service, rag_service


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Point the SQLite layer at a throwaway file so cache tests are hermetic."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db, "_initialized", False)


def _message(text: str):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason="end_turn",
    )


def _candidate(source: str, section: str, text: str, distance=0.5):
    return {
        "id": f"{source}:{section}",
        "document": f"{source} § {section}\n\n{text}",
        "metadata": {"source": source, "section": section},
        "distance": distance,
    }


@pytest.fixture
def stubbed(monkeypatch, tmp_db):
    """Common stubs: three candidates (two sharing a source/section), a
    structured Claude reply that used blocks 1 and 3, and a fixed index version."""
    candidates = [
        _candidate("economy.md", "Weapon prices", "Phantom costs 2,900."),
        _candidate("maps.md", "Ascent", "Mid control map."),
        _candidate("economy.md", "Weapon prices", "Vandal also 2,900."),
    ]
    monkeypatch.setattr(rag_service, "_retrieve", lambda q, n_results=8: (candidates, 0.5))
    monkeypatch.setattr(rag_service, "index_version", lambda: "v1")
    monkeypatch.setattr(rag_service, "corpus_vintage", lambda: "notes current to patch 13.05 (2026-09-01)")

    calls = {"create": 0, "ask": 0}

    def fake_create(**kwargs):
        calls["create"] += 1
        calls["create_kwargs"] = kwargs
        return _message(json.dumps({"answer": "A Phantom costs 2,900 credits.", "used_sources": [1, 3]}))

    def fake_ask(prompt, system=None, max_tokens=4000):
        calls["ask"] += 1
        calls["ask_system"] = system
        return "Outside my notes: general answer."

    monkeypatch.setattr(claude_service, "_create", fake_create)
    monkeypatch.setattr(claude_service, "ask_claude", fake_ask)
    return calls


class TestUsedSources:
    def test_used_flags_follow_claudes_used_sources(self, stubbed):
        result = rag_service.ask_meta("How much does a Phantom cost?")
        assert result["answer"] == "A Phantom costs 2,900 credits."
        # Blocks 1 and 3 are both (economy.md, Weapon prices) — deduped into
        # one used chip; the maps.md chip (block 2) is present but unused.
        assert result["sources"] == [
            {
                "source": "economy.md",
                "section": "Weapon prices",
                "snippet": "Phantom costs 2,900.",
                "used": True,
            },
            {
                "source": "maps.md",
                "section": "Ascent",
                "snippet": "Mid control map.",
                "used": False,
            },
        ]
        assert result["corpus_vintage"] == "notes current to patch 13.05 (2026-09-01)"

    def test_snippets_do_not_leak_the_embedded_context_header(self, stubbed):
        result = rag_service.ask_meta("How much does a Phantom cost?")
        for entry in result["sources"]:
            assert "§" not in entry["snippet"]

    def test_out_of_range_block_numbers_are_ignored(self, stubbed, monkeypatch):
        monkeypatch.setattr(
            claude_service,
            "_create",
            lambda **kw: _message(json.dumps({"answer": "ok", "used_sources": [2, 99, -1]})),
        )
        result = rag_service.ask_meta("q1")
        used = [s for s in result["sources"] if s.get("used")]
        assert [s["source"] for s in used] == ["maps.md"]

    def test_malformed_json_degrades_to_raw_text_without_used_flags(self, stubbed, monkeypatch):
        monkeypatch.setattr(claude_service, "_create", lambda **kw: _message("not json at all"))
        result = rag_service.ask_meta("q2")
        assert result["answer"] == "not json at all"
        assert all("used" not in s for s in result["sources"])
        assert len(result["sources"]) == 2

    def test_vintage_line_reaches_the_system_prompt(self, stubbed):
        rag_service.ask_meta("q3")
        system = stubbed["create_kwargs"]["system"]
        assert "notes current to patch 13.05 (2026-09-01)" in system
        assert "Today's date" in system


class TestTwoTier:
    def test_far_distance_answers_without_context(self, stubbed, monkeypatch):
        far = [_candidate("economy.md", "Weapon prices", "irrelevant", distance=1.9)]
        monkeypatch.setattr(rag_service, "_retrieve", lambda q, n_results=8: (far, 1.9))
        result = rag_service.ask_meta("What is a good recipe for banana bread?")
        assert result["sources"] == []
        assert result["answer"].startswith("Outside my notes:")
        assert stubbed["ask"] == 1 and stubbed["create"] == 0
        assert "found nothing relevant" in stubbed["ask_system"]

    def test_empty_retrieval_also_falls_back(self, stubbed, monkeypatch):
        monkeypatch.setattr(rag_service, "_retrieve", lambda q, n_results=8: ([], None))
        result = rag_service.ask_meta("anything")
        assert result["sources"] == []
        assert stubbed["ask"] == 1

    def test_close_distance_uses_context(self, stubbed):
        rag_service.ask_meta("How much does a Phantom cost?")
        assert stubbed["create"] == 1 and stubbed["ask"] == 0


class TestAnswerCache:
    def test_repeat_question_is_served_from_cache(self, stubbed):
        first = rag_service.ask_meta("How much does a Phantom cost?")
        second = rag_service.ask_meta("How much does a Phantom cost?")
        assert stubbed["create"] == 1, "second ask must not reach Claude"
        assert second == first

    def test_normalization_collapses_case_and_whitespace(self, stubbed):
        rag_service.ask_meta("How much does a Phantom cost?")
        rag_service.ask_meta("  how MUCH does a\tphantom cost?  ")
        assert stubbed["create"] == 1

    def test_different_question_misses_the_cache(self, stubbed):
        rag_service.ask_meta("How much does a Phantom cost?")
        rag_service.ask_meta("How much does a Vandal cost?")
        assert stubbed["create"] == 2

    def test_index_version_change_invalidates(self, stubbed, monkeypatch):
        rag_service.ask_meta("How much does a Phantom cost?")
        monkeypatch.setattr(rag_service, "index_version", lambda: "v2")
        rag_service.ask_meta("How much does a Phantom cost?")
        assert stubbed["create"] == 2, "a reindexed corpus must not serve stale answers"

    def test_fallback_answers_are_cached_too(self, stubbed, monkeypatch):
        monkeypatch.setattr(rag_service, "_retrieve", lambda q, n_results=8: ([], None))
        rag_service.ask_meta("off-topic question")
        rag_service.ask_meta("off-topic question")
        assert stubbed["ask"] == 1

    def test_prune_drops_rows_from_older_corpora(self, tmp_db):
        db.put_meta_answer("h1", "old-version", {"answer": "stale"})
        db.put_meta_answer("h2", "new-version", {"answer": "fresh"})
        assert db.get_meta_answer("h1", "old-version") is None
        assert db.get_meta_answer("h2", "new-version") == {"answer": "fresh"}


class TestCorpusVintage:
    def test_fallback_constant_when_no_front_matter(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rag_service, "KNOWLEDGE_DIR", tmp_path)
        (tmp_path / "a.md").write_text("# A\n\n## S\nbody\n", encoding="utf-8")
        assert rag_service.corpus_vintage() == rag_service.CORPUS_VINTAGE_FALLBACK

    def test_latest_patch_metadata_wins(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rag_service, "KNOWLEDGE_DIR", tmp_path)
        (tmp_path / "old.md").write_text(
            "---\npatch: 13.04\ndate: 2026-08-18\n---\n# O\n\n## S\nbody\n", encoding="utf-8"
        )
        (tmp_path / "new.md").write_text(
            "---\npatch: 13.05\ndate: 2026-09-01\n---\n# N\n\n## S\nbody\n", encoding="utf-8"
        )
        assert rag_service.corpus_vintage() == "notes current to patch 13.05 (2026-09-01)"

    def test_real_corpus_reports_the_ingested_patch(self):
        """The checked-in corpus carries patch front matter from the ingestion
        script; the vintage must come from it, never from file mtimes."""
        vintage = rag_service.corpus_vintage()
        assert vintage.startswith("notes current to patch ")

    def test_index_version_changes_with_corpus_content(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rag_service, "KNOWLEDGE_DIR", tmp_path)
        monkeypatch.setattr(rag_service, "_index_version", None)
        (tmp_path / "a.md").write_text("# A\n\n## S\nbody one\n", encoding="utf-8")
        v1 = rag_service.index_version()
        monkeypatch.setattr(rag_service, "_index_version", None)
        (tmp_path / "a.md").write_text("# A\n\n## S\nbody two\n", encoding="utf-8")
        assert rag_service.index_version() != v1
