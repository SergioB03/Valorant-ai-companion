"""Generate the public patch-digest pages from the RAG knowledge corpus.

Usage (from backend/, using the venv python — bare `python` is the Store stub):

    venv/Scripts/python.exe scripts/generate_patch_digest.py

Reads every data/knowledge/patch-notes-<ver>.md written by
ingest_patch_notes.py (front matter + markdown body) and writes:

    frontend/public/patch/<ver-with-dashes>.html   one digest page per patch
    frontend/public/patch/index.html               the list page
    frontend/public/sitemap.xml                    root + the pages above

The digest is STRUCTURAL on purpose: section/agent/ability names and change
counts, generated from the document's shape — it summarizes and links, it
never reproduces the notes' text (docs/GROWTH-FEATURES.md item 10: the wiki
text is CC BY-SA fan content and the official notes are Riot's; over-quoting
either is the failure mode). Every page carries the CC BY-SA attribution, the
source URL, and the "not official Riot text" disclaimer from front matter.

Maintainer-run, offline, deterministic: no network, no AI calls, and
deliberately NO backend endpoint — a live generation path would be an
unauthenticated spend surface (the open-relay shape SECURITY.md already paid
for once). Review the output, then commit it; the pages deploy with the
frontend like privacy.html does.
"""

from __future__ import annotations

import html
import re
import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
KNOWLEDGE_DIR = BACKEND_DIR / "data" / "knowledge"
PATCH_DIR = REPO_ROOT / "frontend" / "public" / "patch"
SITEMAP_PATH = REPO_ROOT / "frontend" / "public" / "sitemap.xml"

SITE = "https://rebuy.gg"
OFFICIAL_NOTES_URL = "https://playvalorant.com/en-us/news/tags/patch-notes/"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/3.0/"

# Only real per-patch files (patch-notes-13-05.md); patch-notes-recent.md is a
# hand-written aggregate with no front matter and is not a digest source.
FILENAME_RE = re.compile(r"^patch-notes-(\d+)-(\d+)\.md$")

# Same hand-rolled front-matter dialect as app/services/rag_service.py.
FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n", re.DOTALL)

BULLET_RE = re.compile(r"^(\s*)-\s+(.*)$")

# How many named items to show per group before "+N more".
MAX_ITEMS_SHOWN = 6


# --- Parsing ------------------------------------------------------------------


def parse_front_matter(text: str) -> tuple[dict, str]:
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip():
            meta[key.strip()] = value.strip()
    return meta, text[m.end():]


def _is_label(text: str) -> bool:
    """Is this bullet a short name (an ability, a bundle) rather than a change
    sentence? Only labels are safe to print on the public page — printing
    sentences would drift from digest into reproduction."""
    t = text.strip().rstrip(":").strip()
    return 0 < len(t) <= 40 and not t.endswith(".") and len(t.split()) <= 6


def _finish_group(group: dict | None) -> None:
    """Turn a group's raw (indent, text) bullets into counts + named items."""
    if group is None:
        return
    bullets = group.pop("_bullets")
    n = len(bullets)
    for i, (indent, text) in enumerate(bullets):
        is_parent = i + 1 < n and bullets[i + 1][0] > indent
        if is_parent:
            if _is_label(text):
                group["items"].append(text.strip().rstrip(":").strip())
        else:
            group["changes"] += 1
            if "bugfix" in text.lower():
                group["bugfixes"] += 1


def parse_digest(body: str, patch: str) -> dict:
    """Structural summary of one knowledge file's markdown body."""
    sections: list[dict] = []
    section: dict | None = None
    group: dict | None = None
    prefix = f"Patch {patch} — "

    def new_group(name: str) -> dict:
        g = {"name": name, "changes": 0, "bugfixes": 0, "items": [], "_bullets": []}
        section["groups"].append(g)
        return g

    for line in body.splitlines():
        if line.startswith("## "):
            _finish_group(group)
            group = None
            title = line[3:].strip()
            title = title.removeprefix(prefix)
            section = {"title": title, "groups": []}
            sections.append(section)
        elif line.startswith("### ") and section is not None:
            _finish_group(group)
            group = new_group(line[4:].strip())
        elif line.startswith("#### ") and group is not None:
            # H4s (e.g. sub-bundles) stay in the enclosing group: their name
            # becomes an item, their bullets keep counting into the group.
            name = line[5:].strip()
            if _is_label(name):
                group["items"].append(name)
        elif section is not None and (m := BULLET_RE.match(line)):
            if group is None:
                group = new_group("General")
            group["_bullets"].append((len(m.group(1)), m.group(2)))
    _finish_group(group)

    total = sum(g["changes"] for s in sections for g in s["groups"])
    agents = [
        g["name"]
        for s in sections
        if "agent" in s["title"].lower()
        for g in s["groups"]
        if g["name"].lower() != "general"
    ]
    return {"sections": sections, "total_changes": total, "agents": agents}


def load_patches() -> list[dict]:
    patches = []
    for path in sorted(KNOWLEDGE_DIR.glob("patch-notes-*.md")):
        if not FILENAME_RE.match(path.name):
            continue
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        if "patch" not in meta or "source_url" not in meta:
            raise SystemExit(f"{path.name}: missing front matter (patch/source_url)")
        digest = parse_digest(body, meta["patch"])
        patches.append(
            {
                "version": meta["patch"],
                "slug": meta["patch"].replace(".", "-"),
                "date": meta.get("date", ""),
                "fetched": meta.get("fetched", meta.get("date", "")),
                "source_url": meta["source_url"],
                "license": meta.get("license", "CC BY-SA 3.0"),
                **digest,
            }
        )
    # Newest first, numerically (13.10 must sort above 13.9).
    patches.sort(key=lambda p: tuple(int(x) for x in p["version"].split(".")), reverse=True)
    return patches


# --- Rendering ----------------------------------------------------------------


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _pretty_date(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%B %d, %Y").replace(" 0", " ")
    except ValueError:
        return iso


def _group_line(g: dict) -> str | None:
    n, fixes = g["changes"], g["bugfixes"]
    if n == 0 and not g["items"]:
        return None
    if n == 0:
        kind = "additions"
    elif fixes == n:
        kind = f"{n} bugfix" + ("es" if n != 1 else "")
    elif fixes:
        kind = f"{n} changes, {fixes} of them bugfixes"
    else:
        kind = f"{n} change" + ("s" if n != 1 else "")
    shown = g["items"][:MAX_ITEMS_SHOWN]
    extra = len(g["items"]) - len(shown)
    detail = ""
    if shown:
        detail = " — " + ", ".join(_esc(i) for i in shown)
        if extra > 0:
            detail += f" +{extra} more"
    return f"<li><strong>{_esc(g['name'])}</strong> &middot; {kind}{detail}</li>"


# Design tokens copied from privacy.html / src/index.css — these pages are
# static and self-contained, same pattern as the privacy page.
STYLE = """\
      :root {
        --bg: #0f1923;
        --panel: rgba(23, 32, 42, 0.93);
        --panel-2: rgba(15, 23, 32, 0.92);
        --border: #2c3944;
        --accent: #ff4655;
        --text: #ece8e1;
        --muted: #9aa7b3;
        --cyan: #7dd3fc;
        --cut: 12px;
        --display: "Bebas Neue", "Arial Narrow", Impact, sans-serif;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        background: var(--bg);
        color: var(--text);
        font-family: "Inter", "Segoe UI", ui-sans-serif, system-ui, sans-serif;
        font-size: 15px;
        line-height: 1.6;
        -webkit-font-smoothing: antialiased;
      }
      .wrap {
        max-width: 720px;
        margin: 0 auto;
        padding: 32px 20px 64px;
      }
      .top-glow {
        position: fixed;
        inset: 0 0 auto 0;
        height: 3px;
        background: linear-gradient(90deg, transparent, var(--accent) 30%, var(--accent) 70%, transparent);
        pointer-events: none;
      }
      h1 {
        font-family: var(--display);
        font-size: 34px;
        font-weight: 400;
        font-style: italic;
        letter-spacing: 3px;
        text-transform: uppercase;
        line-height: 1.05;
        margin: 18px 0 4px;
      }
      .sub { color: var(--muted); font-size: 13px; margin: 0 0 24px; }
      .panel {
        background: var(--panel);
        border: 1px solid var(--border);
        padding: 20px;
        position: relative;
        margin-bottom: 16px;
        clip-path: polygon(0 0, 100% 0, 100% calc(100% - var(--cut)), calc(100% - var(--cut)) 100%, 0 100%);
      }
      .panel::before {
        content: "";
        position: absolute;
        top: 0; left: 0;
        width: 42px; height: 3px;
        background: var(--accent);
      }
      h2 {
        font-family: var(--display);
        font-size: 22px;
        font-weight: 400;
        font-style: italic;
        letter-spacing: 2px;
        text-transform: uppercase;
        margin: 0 0 8px;
      }
      p, li { color: var(--text); }
      .muted { color: var(--muted); }
      ul { margin: 8px 0; padding-left: 20px; }
      li { margin: 3px 0; }
      a { color: var(--cyan); }
      .back {
        display: inline-block;
        margin: 0 8px 8px 0;
        color: var(--muted);
        font-size: 13px;
        text-decoration: none;
        border: 1px solid var(--border);
        padding: 6px 14px;
      }
      .back:hover { border-color: var(--accent); color: var(--text); }
      .pills { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 2px; padding: 0; list-style: none; }
      .pills li {
        border: 1px solid var(--border);
        background: var(--panel-2);
        color: var(--muted);
        font-size: 13px;
        padding: 4px 10px;
        margin: 0;
      }
      .pills li strong { color: var(--text); font-weight: 600; }
      .patch-link {
        font-family: var(--display);
        font-size: 22px;
        font-style: italic;
        letter-spacing: 2px;
        text-transform: uppercase;
        text-decoration: none;
      }
"""

FAVICON = (
    "data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox="
    "'0%200%2032%2032'%3E%3Crect%20width='32'%20height='32'%20fill='%230f1923'"
    "/%3E%3Cpath%20fill='%23ff4655'%20d='M4%207l11%2014h6L8%207H4zm24%200h-6l-7"
    "%209%203%204L28%207z'/%3E%3C/svg%3E"
)


def _head(title: str, description: str, canonical: str) -> str:
    return f"""\
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="color-scheme" content="dark" />
    <meta name="description" content="{_esc(description)}" />
    <link rel="canonical" href="{_esc(canonical)}" />
    <meta property="og:type" content="article" />
    <meta property="og:site_name" content="Valorant AI Companion" />
    <meta property="og:title" content="{_esc(title)}" />
    <meta property="og:description" content="{_esc(description)}" />
    <meta property="og:url" content="{_esc(canonical)}" />
    <meta property="og:image" content="{SITE}/og-card.png" />
    <meta property="og:image:width" content="1200" />
    <meta property="og:image:height" content="630" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{_esc(title)}" />
    <meta name="twitter:description" content="{_esc(description)}" />
    <meta name="twitter:image" content="{SITE}/og-card.png" />
    <link rel="icon" href="{FAVICON}" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@400;600;700&display=swap"
      rel="stylesheet"
    />
    <title>{_esc(title)}</title>
    <style>
{STYLE}    </style>
  </head>"""


def _attribution_panel(p: dict | None) -> str:
    if p is not None:
        derived = (
            f'Derived from the community <a href="{_esc(p["source_url"])}" '
            f'rel="noopener noreferrer">VALORANT Wiki page for patch '
            f"{_esc(p['version'])}</a>, adapted under "
        )
    else:
        derived = "Each digest is derived from its community VALORANT Wiki page (linked on the page), adapted under "
    return f"""\
      <div class="panel">
        <h2>Attribution &amp; license</h2>
        <p class="muted">
          {derived}<a href="{LICENSE_URL}" rel="noopener noreferrer">CC BY-SA 3.0</a>
          &mdash; see the source page for its authors. This digest text is
          likewise available under CC BY-SA 3.0.
        </p>
        <p class="muted">
          This is a summary, <strong>not official Riot text</strong>: for exact
          values always read the
          <a href="{OFFICIAL_NOTES_URL}" rel="noopener noreferrer">official
          patch notes at playvalorant.com</a>. This project is a hobby project,
          not affiliated with or endorsed by Riot Games.
        </p>
      </div>"""


def render_patch_page(p: dict) -> str:
    title = f"VALORANT Patch {p['version']} digest — what changed, at a glance"
    n_sections = len(p["sections"])
    agents = p["agents"]
    description = (
        f"Patch {p['version']} ({_pretty_date(p['date'])}) in one screen: "
        f"~{p['total_changes']} changes across {n_sections} areas"
        + (f", touching {', '.join(agents[:4])}" + (" and more" if len(agents) > 4 else "") if agents else "")
        + ". A community digest linking to the official notes — from the Valorant AI Companion."
    )
    canonical = f"{SITE}/patch/{p['slug']}.html"

    glance_pills = [
        f"<li><strong>~{p['total_changes']}</strong> changes</li>",
        f"<li><strong>{n_sections}</strong> areas</li>",
    ]
    if agents:
        glance_pills.append(f"<li>Agents: <strong>{_esc(', '.join(agents))}</strong></li>")

    section_panels = []
    for s in p["sections"]:
        lines = [line for g in s["groups"] if (line := _group_line(g))]
        if not lines:
            continue
        section_panels.append(
            '      <div class="panel">\n'
            f"        <h2>{_esc(s['title'])}</h2>\n"
            "        <ul>\n"
            + "\n".join(f"          {line}" for line in lines)
            + "\n        </ul>\n      </div>"
        )

    return f"""<!doctype html>
<html lang="en">
{_head(title, description, canonical)}
  <body>
    <div class="top-glow"></div>
    <div class="wrap">
      <a class="back" href="/">&larr; Back to the app</a>
      <a class="back" href="/patch/">All patch digests</a>
      <h1>Patch {_esc(p['version'])} <span style="color: var(--accent)">digest</span></h1>
      <p class="sub">
        {_esc(_pretty_date(p['date']))} &middot; a structural summary of what the patch
        touches &mdash; names and counts, not the notes themselves
      </p>

      <div class="panel">
        <h2>At a glance</h2>
        <ul class="pills">
          {' '.join(glance_pills)}
        </ul>
      </div>

{chr(10).join(section_panels)}

      <div class="panel">
        <h2>Read the full notes</h2>
        <p>
          This page deliberately stops at names and counts. The actual change
          details live in the
          <a href="{OFFICIAL_NOTES_URL}" rel="noopener noreferrer">official
          patch notes at playvalorant.com</a> and the
          <a href="{_esc(p['source_url'])}" rel="noopener noreferrer">community
          wiki page this digest was built from</a>.
        </p>
        <p class="muted">
          Want to know what it means for your games? Ask the
          <a href="/">Meta Q&amp;A in the app</a> &mdash; it has these notes in
          its knowledge base.
        </p>
      </div>

{_attribution_panel(p)}
    </div>
  </body>
</html>
"""


def render_index(patches: list[dict]) -> str:
    title = "VALORANT patch digests — every patch, at a glance"
    description = (
        "One-screen structural digests of recent VALORANT patches — what each "
        "one touches, linking to the official notes. From the Valorant AI Companion."
    )
    canonical = f"{SITE}/patch/"

    entries = []
    for p in patches:
        agents = p["agents"]
        agent_bit = f" &middot; {_esc(', '.join(agents[:5]))}" + ("&hellip;" if len(agents) > 5 else "") if agents else ""
        entries.append(f"""\
      <div class="panel">
        <p style="margin: 0 0 4px">
          <a class="patch-link" href="/patch/{_esc(p['slug'])}.html">Patch {_esc(p['version'])}</a>
        </p>
        <p class="muted" style="margin: 0">
          {_esc(_pretty_date(p['date']))} &middot; ~{p['total_changes']} changes
          across {len(p['sections'])} areas{agent_bit}
        </p>
      </div>""")

    return f"""<!doctype html>
<html lang="en">
{_head(title, description, canonical)}
  <body>
    <div class="top-glow"></div>
    <div class="wrap">
      <a class="back" href="/">&larr; Back to the app</a>
      <h1>Patch <span style="color: var(--accent)">digests</span></h1>
      <p class="sub">
        What each VALORANT patch touches, on one screen &mdash; structural
        summaries that link to the official notes for the details.
      </p>

{chr(10).join(entries)}

{_attribution_panel(None)}
    </div>
  </body>
</html>
"""


def render_sitemap(patches: list[dict]) -> str:
    latest = max((p["fetched"] for p in patches), default=date.today().isoformat())
    urls = [
        (f"{SITE}/", latest),
        (f"{SITE}/patch/", latest),
    ] + [(f"{SITE}/patch/{p['slug']}.html", p["fetched"]) for p in reversed(patches)]
    body = "\n".join(
        f"  <url>\n    <loc>{_esc(loc)}</loc>\n    <lastmod>{_esc(mod)}</lastmod>\n  </url>"
        for loc, mod in urls
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{body}
</urlset>
"""


# --- Entry point --------------------------------------------------------------


def main() -> int:
    patches = load_patches()
    if not patches:
        print("error: no patch-notes-<ver>.md files with front matter found", file=sys.stderr)
        return 2
    PATCH_DIR.mkdir(parents=True, exist_ok=True)
    for p in patches:
        out = PATCH_DIR / f"{p['slug']}.html"
        out.write_text(render_patch_page(p), encoding="utf-8", newline="\n")
        print(f"wrote {out}  (patch {p['version']}: ~{p['total_changes']} changes, "
              f"{len(p['sections'])} areas)")
    index_path = PATCH_DIR / "index.html"
    index_path.write_text(render_index(patches), encoding="utf-8", newline="\n")
    print(f"wrote {index_path}  ({len(patches)} patches)")
    SITEMAP_PATH.write_text(render_sitemap(patches), encoding="utf-8", newline="\n")
    print(f"wrote {SITEMAP_PATH}")
    print("\nNext: review the pages, then commit them — they deploy with the "
          "frontend exactly like privacy.html.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
