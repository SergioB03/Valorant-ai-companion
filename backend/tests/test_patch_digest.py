"""The patch-digest generator: summarize-and-link, never reproduce.

The generator is offline and deterministic (no AI, no network, no endpoint),
so its contract is testable directly: digests are built from the documents'
STRUCTURE (names + counts), every page carries the CC BY-SA attribution +
source URL + "not official Riot text" disclaimer, and no change sentence from
the corpus ever lands verbatim on a public page.
"""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_patch_digest.py"
_spec = importlib.util.spec_from_file_location("generate_patch_digest", _SCRIPT)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


SAMPLE_BODY = """\
# VALORANT Patch 9.99 — Patch Notes (January 1, 2026)

Preamble paragraph that the digest must ignore.

## Patch 9.99 — Agent Updates
### General
- Bugfix: Ultimate VO could continue playing from an enemy's perspective.

### Cypher
- Trapwire
  - Bugfix: Debuff persists indefinitely on a new target.
- Cyber Cage
  - Bugfix: Incorrectly blocking flashes and detection.

### Jett
- Tailwind
  - Dash distance increased 5%.

## Patch 9.99 — Modes Updates
### Premier
- Stage will run for five weeks instead of the usual seven.
- Teams with a Premier Score of at least 450 qualify for Playoffs.
  - In Contender and Invite, qualification is still based on placement.

## Patch 9.99 — Cosmetic Updates
- Adjusted the sound attenuation for all sound sprays.
### Champions Bundle
#### Broadcast Drops
- Stamp of Approval spray
"""


class TestParseDigest:
    def setup_method(self):
        self.d = gen.parse_digest(SAMPLE_BODY, "9.99")

    def test_sections_lose_the_patch_prefix(self):
        assert [s["title"] for s in self.d["sections"]] == [
            "Agent Updates", "Modes Updates", "Cosmetic Updates",
        ]

    def test_leaf_bullets_are_counted_and_classified(self):
        agent = self.d["sections"][0]
        cypher = next(g for g in agent["groups"] if g["name"] == "Cypher")
        assert cypher["changes"] == 2
        assert cypher["bugfixes"] == 2
        jett = next(g for g in agent["groups"] if g["name"] == "Jett")
        assert (jett["changes"], jett["bugfixes"]) == (1, 0)

    def test_only_short_labels_become_named_items(self):
        """Ability names are safe to print; sentence-shaped parent bullets
        (Premier's qualification rules) must stay anonymous counts."""
        agent = self.d["sections"][0]
        cypher = next(g for g in agent["groups"] if g["name"] == "Cypher")
        assert cypher["items"] == ["Trapwire", "Cyber Cage"]
        premier = self.d["sections"][1]["groups"][0]
        assert premier["items"] == []
        assert premier["changes"] == 2  # both leaves still counted

    def test_bullets_before_any_h3_get_an_implicit_general_group(self):
        cosmetics = self.d["sections"][2]
        assert cosmetics["groups"][0]["name"] == "General"
        assert cosmetics["groups"][0]["changes"] == 1

    def test_h4_names_fold_into_the_enclosing_group(self):
        bundle = next(
            g for g in self.d["sections"][2]["groups"] if g["name"] == "Champions Bundle"
        )
        assert "Broadcast Drops" in bundle["items"]

    def test_agents_come_from_the_agent_section_minus_general(self):
        assert self.d["agents"] == ["Cypher", "Jett"]

    def test_total_counts_every_leaf(self):
        # General 1 + Cypher 2 + Jett 1 + Premier 2 + cosmetics General 1
        # + Champions Bundle 1
        assert self.d["total_changes"] == 8


def _sample_patch() -> dict:
    return {
        "version": "9.99",
        "slug": "9-99",
        "date": "2026-01-01",
        "fetched": "2026-01-02",
        "source_url": "https://wiki.playvalorant.com/en-us/Patch_Notes/9.99",
        "license": "CC BY-SA 3.0",
        **gen.parse_digest(SAMPLE_BODY, "9.99"),
    }


class TestRenderedPages:
    def setup_method(self):
        self.patch = _sample_patch()
        self.page = gen.render_patch_page(self.patch)
        self.index = gen.render_index([self.patch])

    def test_every_page_carries_attribution_and_disclaimers(self):
        for page in (self.page, self.index):
            assert "CC BY-SA 3.0" in page
            assert "not official Riot text" in page
            assert "not affiliated with or endorsed by Riot Games" in page
            assert "playvalorant.com" in page
        # The per-patch page links its own source URL.
        assert self.patch["source_url"] in self.page

    def test_change_text_is_never_reproduced(self):
        """The whole point of a digest: names and counts, not the notes."""
        for sentence in (
            "Debuff persists indefinitely on a new target",
            "Dash distance increased 5%",
            "qualification is still based on placement",
            "Adjusted the sound attenuation",
        ):
            assert sentence not in self.page

    def test_named_items_and_counts_do_appear(self):
        assert "Trapwire" in self.page
        assert "Cyber Cage" in self.page
        assert "2 bugfixes" in self.page

    def test_pages_are_indexable_and_canonical(self):
        assert "noindex" not in self.page
        assert 'rel="canonical" href="https://rebuy.gg/patch/9-99.html"' in self.page
        assert 'rel="canonical" href="https://rebuy.gg/patch/"' in self.index


class TestRealCorpus:
    """The repo's own knowledge files must keep parsing — this is what the
    committed pages under frontend/public/patch/ are generated from."""

    def test_both_shipped_patches_load_newest_first(self):
        patches = gen.load_patches()
        versions = [p["version"] for p in patches]
        assert versions[:2] == ["13.05", "13.04"]

    def test_the_aggregate_summary_file_is_not_a_digest_source(self):
        patches = gen.load_patches()
        assert all(p["version"].count(".") == 1 for p in patches)

    def test_sitemap_lists_root_index_and_every_patch(self):
        patches = gen.load_patches()
        sitemap = gen.render_sitemap(patches)
        assert "<loc>https://rebuy.gg/</loc>" in sitemap
        assert "<loc>https://rebuy.gg/patch/</loc>" in sitemap
        for p in patches:
            assert f"<loc>https://rebuy.gg/patch/{p['slug']}.html</loc>" in sitemap
