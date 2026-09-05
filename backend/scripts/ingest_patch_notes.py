"""Fetch VALORANT patch notes from the community wiki into the RAG corpus.

Usage (from backend/, using the venv python — bare `python` is the Store stub):

    venv/Scripts/python.exe scripts/ingest_patch_notes.py 13.05 [13.04 ...]

For each patch version this fetches the wikitext of
https://wiki.playvalorant.com/en-us/Patch_Notes/<version> via the MediaWiki API
(the only structured patch-notes feed that exists — HenrikDev, valorant-api.com
and playvalorant.com have none), converts it to the corpus' markdown dialect
('## ' section headings, so rag_service.chunk_markdown works unchanged), and
writes data/knowledge/patch-notes-<version-with-dashes>.md with:

  - a '---' front-matter block carrying {patch, date, source_url, license,
    fetched} — rag_service reads patch/date for corpus_vintage() and the
    answer-cache index_version;
  - an attribution preamble (community-sourced summary, not official Riot
    text; CC BY-SA 3.0) which the chunker deliberately does NOT index.

MANUAL REFRESH WORKFLOW (commit-and-deploy — deliberately no prod plumbing):
  1. Riot ships a patch (~every 2 weeks). Run this script with the new version.
  2. Read the generated file — wikitext edge cases happen; fix by hand or
     tweak the converter.
  3. Add 2-3 questions about the patch to tests/eval/gold_set.json and run the
     retrieval eval (see tests/eval/test_rag_eval.py) to confirm they hit.
  4. Commit the new knowledge file and push. The normal deploy re-embeds the
     index at Docker build time; nothing on the box changes or schedules.
Automation (a systemd timer) stays deferred until the manual run has survived
a few patches' worth of wikitext quirks.

License note: wiki text is CC BY-SA 3.0 and is fan content, not official Riot
text — every generated file says so in its (un-indexed) preamble and keeps the
source URL in front matter.
"""

import re
import sys
from datetime import date, datetime
from pathlib import Path

import httpx

API_URL = "https://wiki.playvalorant.com/en-us/api.php"
PAGE_TEMPLATE = "Patch_Notes/{version}"
SOURCE_URL_TEMPLATE = "https://wiki.playvalorant.com/en-us/Patch_Notes/{version}"
KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "data" / "knowledge"
USER_AGENT = "valorant-ai-companion corpus ingester (github.com/SergioB03/Valorant-ai-companion)"

# Templates whose first positional argument IS the text we want.
_KEEP_FIRST_ARG = {"ai", "abi text", "collection", "capsule", "patchv", "omega", "ui text"}


def fetch_wikitext(version: str) -> str:
    params = {
        "action": "parse",
        "page": PAGE_TEMPLATE.format(version=version),
        "prop": "wikitext",
        "format": "json",
        "formatversion": "2",
    }
    resp = httpx.get(
        API_URL,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
        follow_redirects=True,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise SystemExit(f"MediaWiki API error for {version}: {data['error'].get('info')}")
    return data["parse"]["wikitext"]


def extract_date(wikitext: str) -> str:
    """ISO date from the Infobox '|date = September 1st, 2026' line."""
    m = re.search(r"^\|\s*date\s*=\s*(.+?)\s*$", wikitext, re.MULTILINE)
    if not m:
        raise SystemExit(
            "No '|date =' line found in the Infobox — fix the page or hardcode the "
            "date in the generated file's front matter."
        )
    raw = re.sub(r"(\d{1,2})(st|nd|rd|th)", r"\1", m.group(1))
    try:
        return datetime.strptime(raw, "%B %d, %Y").date().isoformat()
    except ValueError:
        raise SystemExit(f"Could not parse Infobox date {m.group(1)!r} — expected 'Month DDth, YYYY'.")


def _replace_template(match: re.Match) -> str:
    inner = match.group(1)
    parts = inner.split("|")
    name = parts[0].strip().lower()
    if name in _KEEP_FIRST_ARG and len(parts) > 1:
        # First positional (non key=value) argument is the display text.
        for arg in parts[1:]:
            if "=" not in arg:
                return arg.strip()
    return ""  # navigation/icon/layout templates ({{ui|..}}, {{clear}}, Infobox, ...)


def wikitext_to_markdown(wikitext: str, version: str) -> str:
    text = wikitext

    # Drop media/navigation noise before template expansion.
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<gallery[^>]*>.*?</gallery>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"\[\[File:[^\]]*\]\]", "", text)
    text = re.sub(r"\[\[Category:[^\]]*\]\]", "", text)

    # Expand/remove templates innermost-first so nesting ({{Infobox ... {{collection|X}}}})
    # resolves before the outer block is dropped.
    for _ in range(10):
        new = re.sub(r"\{\{([^{}]*)\}\}", _replace_template, text)
        if new == text:
            break
        text = new

    # Links: [[target|label]] -> label, [[target]] -> target, [url label] -> label.
    text = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", text)

    # Bold/italics.
    text = text.replace("'''", "").replace("''", "")

    # Headings, deepest first. H2 gets the patch version prefixed: section names
    # like "Agent Updates" repeat in every patch file, and the prefix keeps both
    # the citation chips and the embedded contextual header unambiguous.
    text = re.sub(r"^====\s*(.*?)\s*====\s*$", r"#### \1", text, flags=re.MULTILINE)
    text = re.sub(r"^===\s*(.*?)\s*===\s*$", r"### \1", text, flags=re.MULTILINE)
    text = re.sub(
        r"^==\s*(.*?)\s*==\s*$", rf"## Patch {version} — \1", text, flags=re.MULTILINE
    )

    # Bullets: *, **, *** -> markdown dashes with indentation.
    text = re.sub(r"^\*\*\*\s*", "    - ", text, flags=re.MULTILINE)
    text = re.sub(r"^\*\*\s*", "  - ", text, flags=re.MULTILINE)
    text = re.sub(r"^\*\s*", "- ", text, flags=re.MULTILINE)

    # Whitespace hygiene: trailing spaces, collapsed blank runs.
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_file(version: str, iso_date: str, body_markdown: str) -> str:
    source_url = SOURCE_URL_TEMPLATE.format(version=version)
    pretty_date = date.fromisoformat(iso_date).strftime("%B %d, %Y").replace(" 0", " ")
    return f"""---
patch: {version}
date: {iso_date}
source_url: {source_url}
license: CC BY-SA 3.0
fetched: {date.today().isoformat()}
---

# VALORANT Patch {version} — Patch Notes ({pretty_date})

Community-sourced summary of patch {version} from the VALORANT Wiki
({source_url}), not official Riot text. Text adapted under CC BY-SA 3.0 —
see the source page for its authors. This project is not endorsed by Riot
Games; for exact values always check the official notes at playvalorant.com.

{body_markdown}
"""


def main(argv: list[str]) -> int:
    versions = [v for v in argv if re.fullmatch(r"\d+\.\d+", v)]
    if not versions or versions != argv:
        print(__doc__)
        print("error: pass one or more patch versions like 13.05", file=sys.stderr)
        return 2
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    for version in versions:
        wikitext = fetch_wikitext(version)
        iso_date = extract_date(wikitext)
        markdown = wikitext_to_markdown(wikitext, version)
        out_path = KNOWLEDGE_DIR / f"patch-notes-{version.replace('.', '-')}.md"
        out_path.write_text(build_file(version, iso_date, markdown), encoding="utf-8", newline="\n")
        print(f"wrote {out_path} (patch {version}, {iso_date}, {len(markdown)} chars)")
    print(
        "\nNext: review the file(s), add 2-3 gold-set questions per patch "
        "(tests/eval/gold_set.json), run the eval, then commit — the deploy "
        "re-embeds the index at build time."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
