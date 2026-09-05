"""Chunker unit tests — pure functions, no chroma, no network.

These pin the four measured chunker defects fixed in 2026-09's RAG pass:
cross-section merges, mid-word cuts, indexed disclaimer preambles, and the
missing contextual headers at ingest (tested via a fake collection).
"""

import pytest
from app.services import rag_service
from app.services.rag_service import (
    MAX_CHUNK_CHARS,
    _front_matter,
    _split_long,
    chunk_markdown,
)

SAMPLE = """# Sample Doc — Title

Snapshot from training data (late 2025). This disclaimer used to rank #1
for real questions, which is why preambles are no longer indexed.

## Alpha

Alpha line one about dashing and entry fragging.
Alpha line two.

## Beta

Beta content that is deliberately short.
"""


class TestFrontMatter:
    def test_absent_block_returns_text_unchanged(self):
        meta, rest = _front_matter("# Title\n\nBody\n")
        assert meta == {}
        assert rest == "# Title\n\nBody\n"

    def test_block_is_parsed_and_stripped(self):
        text = "---\npatch: 13.05\ndate: 2026-09-01\n---\n# Title\n\n## S\nBody\n"
        meta, rest = _front_matter(text)
        assert meta == {"patch": "13.05", "date": "2026-09-01"}
        assert rest.startswith("# Title")

    def test_front_matter_never_reaches_chunks(self):
        text = "---\npatch: 13.05\ndate: 2026-09-01\n---\n# T\n\n## S\nBody text here.\n"
        chunks = chunk_markdown(text, "t.md")
        assert all("13.05" not in c["text"] or "patch:" not in c["text"] for c in chunks)
        assert all("---" not in c["text"] for c in chunks)


class TestPreamble:
    def test_disclaimer_preamble_is_not_indexed(self):
        """The space between the H1 and the first '## ' is front matter by
        convention (snapshot disclaimers, attribution) — a live probe showed a
        disclaimer outranking every real chunk for an example-chip question."""
        chunks = chunk_markdown(SAMPLE, "sample.md")
        assert all("Snapshot from training data" not in c["text"] for c in chunks)
        # And no chunk labelled with the filename-as-section degenerate form.
        assert all(c["metadata"]["section"] != "sample.md" for c in chunks)

    def test_file_without_headings_still_indexed_as_overview(self):
        chunks = chunk_markdown("# Only a Title\n\nJust one paragraph of content.", "flat.md")
        assert len(chunks) == 1
        assert chunks[0]["metadata"]["section"] == "Overview"
        assert "Just one paragraph" in chunks[0]["text"]

    def test_empty_text_yields_no_chunks(self):
        assert chunk_markdown("", "x.md") == []
        assert chunk_markdown("   \n\n  ", "x.md") == []


class TestSectionLabels:
    def test_every_chunk_is_labelled_with_its_own_section(self):
        chunks = chunk_markdown(SAMPLE, "sample.md")
        sections = {c["metadata"]["section"] for c in chunks}
        assert sections == {"Alpha", "Beta"}

    def test_short_chunks_never_merge_across_sections(self):
        """The old merge glued a <200-char chunk under the PREVIOUS section's
        label (the agents meta-sentiment chunk was filed as 'Sentinels')."""
        text = "## First\n\nFirst body long enough " + "x" * 300 + "\n\n## Second\n\nshort"
        chunks = chunk_markdown(text, "t.md")
        by_section = {c["metadata"]["section"]: c["text"] for c in chunks}
        assert "short" in by_section["Second"]
        assert "short" not in by_section["First"]

    def test_short_chunks_do_merge_within_a_section(self):
        long_line = "y" * (MAX_CHUNK_CHARS - 10)
        text = f"## Only\n\n{long_line}\n{'z' * 50}"
        chunks = chunk_markdown(text, "t.md")
        assert all(c["metadata"]["section"] == "Only" for c in chunks)

    def test_ids_are_stable_and_unique(self):
        chunks = chunk_markdown(SAMPLE, "sample.md")
        ids = [c["id"] for c in chunks]
        assert len(ids) == len(set(ids))
        assert all(i.startswith("sample.md:") for i in ids)


class TestSplitLong:
    def test_short_text_is_untouched(self):
        assert _split_long("hello", 100) == ["hello"]

    def test_split_prefers_line_boundaries(self):
        text = "\n".join(f"line {i} " + "a" * 40 for i in range(30))
        pieces = _split_long(text, 300)
        assert all(len(p) <= 300 for p in pieces)
        for piece in pieces:
            assert piece.splitlines()[0].startswith("line ")

    def test_oversized_single_line_is_never_cut_mid_word(self):
        """The old code did piece[:limit], producing continuation chunks that
        start mid-word (unfindable by embedding search)."""
        words = ("valorant " * 400).strip()
        pieces = _split_long(words, 250)
        assert len(pieces) > 1
        rebuilt = " ".join(" ".join(p.split()) for p in pieces)
        assert rebuilt == words
        for piece in pieces:
            assert not piece.startswith("alorant"), "mid-word cut leaked through"
            assert all(w == "valorant" for w in piece.split())

    def test_sentence_boundary_preferred_when_available(self):
        text = ("This is a sentence. " * 40).strip()
        pieces = _split_long(text, 200)
        assert all(len(p) <= 200 for p in pieces)
        assert all(p.startswith("This") for p in pieces)


class FakeCollection:
    def __init__(self):
        self.added = None

    def add(self, ids, documents, metadatas):
        self.added = {"ids": ids, "documents": documents, "metadatas": metadatas}


class TestIngestContextualHeaders:
    @pytest.fixture
    def knowledge_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rag_service, "KNOWLEDGE_DIR", tmp_path)
        (tmp_path / "doc.md").write_text(
            "# Doc\n\nPreamble disclaimer.\n\n## Kits\n\nTejo has missiles.\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_documents_are_embedded_with_source_and_section(self, knowledge_dir):
        fake = FakeCollection()
        info = rag_service._ingest(fake)
        assert info == {"documents": 1, "chunks": 1}
        doc = fake.added["documents"][0]
        assert doc.startswith("doc.md § Kits\n\n")
        assert "Tejo has missiles." in doc
        assert fake.added["metadatas"][0] == {"source": "doc.md", "section": "Kits"}

    def test_strip_context_header_round_trips(self, knowledge_dir):
        fake = FakeCollection()
        rag_service._ingest(fake)
        doc = fake.added["documents"][0]
        meta = fake.added["metadatas"][0]
        stripped = rag_service._strip_context_header(doc, meta["source"], meta["section"])
        assert not stripped.startswith("doc.md §")
        assert "Tejo has missiles." in stripped
