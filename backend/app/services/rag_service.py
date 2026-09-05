import hashlib
import json
import re
import threading
from datetime import date
from pathlib import Path

from app import db
from app.services import claude_service

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
CHROMA_DIR = DATA_DIR / "chroma_db"
COLLECTION_NAME = "valorant_knowledge"

MIN_CHUNK_CHARS = 200
MAX_CHUNK_CHARS = 1200

# Bumped whenever chunking or embedding logic changes, so the answer cache and
# index fingerprint distinguish two indexes built from the same files by
# different code. Feeds index_version() below.
CHUNKER_VERSION = 2

# Two-tier answering: when the BEST retrieved chunk is further than this
# (cosine distance), the corpus has nothing relevant and /meta/ask answers from
# model knowledge with an explicit "outside my notes" preface instead of
# injecting misleading chunks. Tuned on tests/eval/gold_set.json (2026-09-05,
# post-chunker-fix index), NOT hardcoded from intuition: every legitimate gold
# question's best hit measured <= 1.371 (worst: the Operator-buy question) and
# every far-domain probe (weather, recipes, taxes) measured >= 1.433, so 1.40
# splits the measured gap. The margin is thin (±0.03) — re-run the eval's
# distance test after ANY corpus or chunker change. Honest limitation, measured
# and kept visible in the eval: NEAR-domain junk — CS2/LoL questions at
# d≈0.95-1.16 — embeds CLOSER than some legitimate hits, so no floor can catch
# it; only the system prompt handles that class.
DISTANCE_FLOOR = 1.40

_client = None
_collection = None
_lock = threading.RLock()
_ready = False
_index_version: str | None = None
_bm25 = None  # lazily built (BM25Okapi, ids, documents, metadatas); reset on reindex

def is_available() -> bool:
    try:
        import chromadb  # noqa: F401
        return True
    except ImportError:
        return False

def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    import chromadb
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    _collection = _client.get_or_create_collection(COLLECTION_NAME)
    return _collection

# --- Corpus front matter ------------------------------------------------------

_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n", re.DOTALL)

def _front_matter(text: str) -> tuple[dict, str]:
    """Parse an optional leading '---' key: value block (hand-rolled, no yaml dep).

    scripts/ingest_patch_notes.py writes {patch, date, ...} here; corpus_vintage()
    and index_version() consume it. Returns ({}, text) when absent.
    """
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip():
            meta[key.strip()] = value.strip()
    return meta, text[m.end():]

# --- Chunking -----------------------------------------------------------------

def _split_long(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    pieces, current = [], ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit and current:
            pieces.append(current)
            current = line
        else:
            current = candidate
    if current:
        pieces.append(current)
    out = []
    for piece in pieces:
        # A single line longer than the limit still has to be cut, but never
        # mid-word: earlier code did piece[:limit] and produced continuation
        # chunks starting mid-word (unfindable by embedding search). Prefer a
        # sentence boundary, then any whitespace, before giving up.
        while len(piece) > limit:
            cut = piece.rfind(". ", limit // 2, limit)
            cut = cut + 1 if cut != -1 else piece.rfind(" ", limit // 2, limit)
            if cut <= 0:
                cut = limit
            out.append(piece[:cut])
            piece = piece[cut:].lstrip()
        out.append(piece)
    return [p.strip() for p in out if p.strip()]

def chunk_markdown(text: str, source: str) -> list[dict]:
    _, text = _front_matter(text)

    sections: list[tuple[str, str]] = []
    heading: str | None = None  # None while inside the preamble
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading is not None and lines:
                sections.append((heading, "\n".join(lines).strip()))
            heading = line[3:].strip()
            lines = [line]
        elif heading is None:
            # Preamble: in this corpus the space between the H1 title and the
            # first '## ' heading is front matter by convention — "snapshot
            # from training data" disclaimers and attribution lines, not
            # answerable content. It is deliberately NOT indexed: a live probe
            # (2026-09-04) showed the agents-meta.md disclaimer ranking #1 for
            # the UI's own "which agents are strong in ranked" example chip,
            # beating every real content chunk. Vintage/attribution now live in
            # the front-matter block and corpus_vintage() instead.
            continue
        else:
            lines.append(line)
    if heading is not None and lines:
        sections.append((heading, "\n".join(lines).strip()))

    # A file with no '## ' headings at all still deserves indexing — treat the
    # whole body as one section rather than silently dropping the file.
    if not sections and text.strip():
        sections = [("Overview", text.strip())]

    raw = []
    for heading, body in sections:
        if not body:
            continue
        for piece in _split_long(body, MAX_CHUNK_CHARS):
            raw.append({"section": heading, "text": piece})

    # Merge undersized neighbours only within the SAME section. The earlier
    # unconditional merge glued a short chunk under the PREVIOUS section's
    # label (e.g. the agents meta-sentiment chunk filed as "Sentinels"),
    # which both mislabelled the citation chip and buried the content.
    merged = []
    for chunk in raw:
        if (
            merged
            and merged[-1]["section"] == chunk["section"]
            and (len(merged[-1]["text"]) < MIN_CHUNK_CHARS or len(chunk["text"]) < MIN_CHUNK_CHARS)
            and len(merged[-1]["text"]) + len(chunk["text"]) + 2 <= MAX_CHUNK_CHARS
        ):
            merged[-1]["text"] += "\n\n" + chunk["text"]
        else:
            merged.append(chunk)

    return [
        {
            "id": f"{source}:{i}",
            "text": chunk["text"],
            "metadata": {"source": source, "section": chunk["section"]},
        }
        for i, chunk in enumerate(merged)
    ]

def _knowledge_files() -> list[Path]:
    if not KNOWLEDGE_DIR.exists():
        return []
    return sorted(KNOWLEDGE_DIR.glob("*.md"))

def _context_header(source: str, section: str) -> str:
    return f"{source} § {section}\n\n"

def _strip_context_header(document: str, source: str, section: str) -> str:
    """Undo _ingest's embedded header so prompts and snippets show clean text."""
    return document.removeprefix(_context_header(source, section))

def _ingest(collection) -> dict:
    files = _knowledge_files()
    ids, documents, metadatas = [], [], []
    for path in files:
        for chunk in chunk_markdown(path.read_text(encoding="utf-8"), path.name):
            ids.append(chunk["id"])
            # Contextual-retrieval-lite: embed each chunk prefixed with its
            # document + section so continuation pieces ("...the rest of Tejo's
            # kit") carry the words a question would actually use. Stripped
            # back off by _strip_context_header before display or prompting.
            meta = chunk["metadata"]
            documents.append(_context_header(meta["source"], meta["section"]) + chunk["text"])
            metadatas.append(meta)
    if ids:
        collection.add(ids=ids, documents=documents, metadatas=metadatas)
    return {"documents": len(files), "chunks": len(ids)}

# --- Index lifecycle ----------------------------------------------------------

def ensure_index() -> dict:
    global _ready, _bm25
    with _lock:
        collection = _get_collection()
        if collection.count() == 0:
            info = _ingest(collection)
            _bm25 = None  # collection content changed; rebuild lazily
        else:
            info = {"documents": len(_knowledge_files()), "chunks": collection.count()}
        _ready = collection.count() > 0
        return info

def reindex() -> dict:
    global _client, _collection, _ready, _index_version, _bm25
    with _lock:
        import chromadb
        _ready = False
        _index_version = None  # corpus may have changed; recompute lazily
        _bm25 = None
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        try:
            _client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        _collection = _client.get_or_create_collection(COLLECTION_NAME)
        info = _ingest(_collection)
        _ready = _collection.count() > 0
        return info

def warm_index_async() -> None:
    """Warm the RAG index on a background daemon thread (called at app startup)."""
    if not is_available():
        return

    def _warm():
        try:
            ensure_index()
        except Exception as e:
            print(f"[rag] background index warm failed: {e}")

    threading.Thread(target=_warm, name="rag-index-warm", daemon=True).start()

def is_ready() -> bool:
    """Cheap request-path readiness: is a non-empty index already built?

    /meta/ask calls this instead of ensure_index() so a missing or corrupt
    collection can never trigger a full corpus re-embed inline on a visitor's
    request (multi-second, under the module lock, serialized against every
    other asker). The non-blocking acquire matters: while the startup warm
    thread (or an admin reindex) holds the lock, this returns False fast and
    the route answers 503 + Retry-After — the state the frontend already
    renders gracefully.
    """
    global _ready
    if _ready:
        return True
    if not is_available():
        return False
    if not _lock.acquire(blocking=False):
        return False  # index build in progress right now
    try:
        try:
            _ready = _get_collection().count() > 0
        except Exception:
            return False
        return _ready
    finally:
        _lock.release()

# --- Corpus metadata ----------------------------------------------------------

# What the vintage line falls back to for the original hand-written corpus,
# which carries no front matter. Kept beside the corpus on purpose: update it
# if those files are ever rewritten from newer knowledge.
CORPUS_VINTAGE_FALLBACK = "training-data snapshot, late 2025 / early 2026"

def corpus_metadata() -> list[dict]:
    """Front matter of every knowledge file, plus its filename."""
    out = []
    for path in _knowledge_files():
        meta, _ = _front_matter(path.read_text(encoding="utf-8"))
        meta["source"] = path.name
        out.append(meta)
    return out

def corpus_vintage() -> str | None:
    """Human-readable freshness line, derived ONLY from explicit per-file
    patch/date front matter (never file mtimes — Docker COPY makes those build
    timestamps, which would fake freshness on every deploy)."""
    dated = [m for m in corpus_metadata() if m.get("patch") and m.get("date")]
    if not dated:
        return CORPUS_VINTAGE_FALLBACK
    latest = max(dated, key=lambda m: m["date"])
    return f"notes current to patch {latest['patch']} ({latest['date']})"

def index_version() -> str:
    """Fingerprint of chunker version + corpus content; keys the answer cache.

    Deterministic across processes (unlike an in-memory counter), so a baked
    Docker index and the answer cache stay consistent across restarts, and any
    corpus edit or chunker change invalidates cached answers on its own.
    """
    global _index_version
    if _index_version is None:
        h = hashlib.sha256(f"chunker-v{CHUNKER_VERSION}".encode())
        for path in _knowledge_files():
            h.update(path.name.encode())
            h.update(path.read_bytes())
        _index_version = h.hexdigest()[:16]
    return _index_version

def status() -> dict:
    documents = len(_knowledge_files())
    vintage = corpus_vintage()
    if not is_available():
        return {"ready": False, "documents": documents, "chunks": 0, "corpus_vintage": vintage}
    chunks = _get_collection().count()
    return {"ready": chunks > 0, "documents": documents, "chunks": chunks, "corpus_vintage": vintage}

# --- Answering ----------------------------------------------------------------

META_SYSTEM_PROMPT = (
    "You are a Valorant knowledge assistant. Prefer the provided context: when it "
    "covers the question, answer from it and cite the sections you used (by their "
    "source file and section name). When the context does not cover the question, "
    "or covers it only partially, answer that part from your own general knowledge "
    "— but explicitly label it as outside the knowledge base and possibly outdated. "
    "Be concise and practical. Plain text only — no markdown headers, asterisks, or "
    "bullet syntax. Use short paragraphs and numbered lines like '1.' at most."
)

# Used when retrieval found nothing within DISTANCE_FLOOR: no context is sent,
# and the answer must open with an explicit outside-my-notes preface.
META_FALLBACK_SYSTEM_PROMPT = (
    "You are a Valorant knowledge assistant. The app's knowledge base was searched "
    "and found nothing relevant to this question, so you are answering purely from "
    "your own general knowledge. Begin your answer with the exact words 'Outside my "
    "notes:' and, if the question is time-sensitive, note that your information may "
    "be outdated. If the question is not about Valorant, say the app only covers "
    "Valorant and answer briefly at most. Be concise and practical. Plain text only "
    "— no markdown headers, asterisks, or bullet syntax."
)

META_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        # Context blocks are numbered [1]..[n] in the prompt; Claude reports
        # which ones the answer actually drew on, driving the sources[].used
        # flags (the frontend badges used chips and de-emphasizes the rest).
        "used_sources": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["answer", "used_sources"],
    "additionalProperties": False,
}

def _system_prompt(base: str) -> str:
    # The single cheapest honesty fix in this feature: tell Claude how old the
    # corpus is and what day it is, so every answer self-caveats staleness.
    return (
        f"{base}\nKnowledge base snapshot: {corpus_vintage()}. "
        f"Today's date is {date.today().isoformat()}."
    )

def _question_hash(question: str) -> str:
    return hashlib.sha256(" ".join(question.lower().split()).encode()).hexdigest()

def _query(question: str, n_results: int = 8) -> dict:
    # Dense (embedding) retrieval. n_results 5→8: at ~525 chars/chunk the 3
    # extra chunks cost fractions of a cent per question and mechanically raise
    # recall. Product code goes through _retrieve (hybrid) below.
    with _lock:
        collection = _get_collection()
        return collection.query(query_texts=[question], n_results=n_results)

# --- Hybrid retrieval (dense + in-process BM25, RRF-fused) --------------------
#
# Eval-gated addition (RA8): after the chunker fixes, the gold set still showed
# two clear lexical misses — exact-token questions like "callouts on Ascent" and
# "patch 13.05 ... smokes" where MiniLM embeddings dilute proper nouns across
# similar sections. BM25 over the same 80-odd chunks catches exactly that class.
# Chroma-native sparse indexing is Cloud-only in chromadb 1.5.9 (and its
# Bm25EmbeddingFunction needs fastembed), so this runs rank-bm25 in-process:
# no Chroma schema changes, no dual-path reindex, corpus small enough that a
# full BM25 scan is microseconds.

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_RRF_K = 60      # standard reciprocal-rank-fusion constant
_HYBRID_POOL = 16  # candidates taken from each retriever before fusion

def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())

def _bm25_index():
    """(BM25Okapi, ids, documents, metadatas) over the whole collection, cached."""
    global _bm25
    if _bm25 is None:
        with _lock:
            if _bm25 is None:
                try:
                    from rank_bm25 import BM25Okapi
                except ImportError:
                    return None  # hybrid degrades to dense-only
                data = _get_collection().get()
                if not data["ids"]:
                    return None
                _bm25 = (
                    BM25Okapi([_tokenize(doc) for doc in data["documents"]]),
                    data["ids"],
                    data["documents"],
                    data["metadatas"],
                )
    return _bm25

def _retrieve(question: str, n_results: int = 8) -> tuple[list[dict], float | None]:
    """Hybrid retrieval: RRF-fused dense + BM25 candidates.

    Returns (candidates, best_dense_distance). Each candidate is
    {"id", "document", "metadata", "distance"} — distance is the dense cosine
    distance, or None for chunks only BM25 surfaced. The two-tier floor uses
    best_dense_distance (DISTANCE_FLOOR is tuned on dense distances; BM25
    scores are corpus-relative and don't transfer between questions).
    """
    res = _query(question, n_results=_HYBRID_POOL)
    ids = res.get("ids", [[]])[0]
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    best_dense = min(dists) if dists else None

    candidates: dict[str, dict] = {}
    scores: dict[str, float] = {}
    for rank, cid in enumerate(ids):
        candidates[cid] = {
            "id": cid,
            "document": docs[rank],
            "metadata": metas[rank],
            "distance": dists[rank] if rank < len(dists) else None,
        }
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (_RRF_K + rank + 1)

    bm = _bm25_index()
    if bm is not None:
        bm25_obj, all_ids, all_docs, all_metas = bm
        bm_scores = bm25_obj.get_scores(_tokenize(question))
        top = sorted(range(len(all_ids)), key=lambda i: bm_scores[i], reverse=True)
        for rank, i in enumerate(top[:_HYBRID_POOL]):
            if bm_scores[i] <= 0:
                break  # zero lexical overlap — don't let noise vote
            cid = all_ids[i]
            if cid not in candidates:
                candidates[cid] = {
                    "id": cid,
                    "document": all_docs[i],
                    "metadata": all_metas[i],
                    "distance": None,
                }
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (_RRF_K + rank + 1)

    ordered = sorted(scores, key=scores.get, reverse=True)[:n_results]
    return [candidates[cid] for cid in ordered], best_dense

def ask_meta(question: str) -> dict:
    # Exact-match answer cache (SQLite): the example chips are one-click
    # questions guaranteed to repeat across visitors, and every repeat is an
    # identical multi-second paid opus call. Keyed on the normalized question +
    # index_version(), so any corpus or chunker change invalidates on its own.
    # Deliberately NOT semantic/similarity caching — a near-miss would serve
    # wrong-patch info. Anthropic prompt caching can't help this flow either:
    # the system prompt is under the minimum cacheable prefix and the retrieved
    # context varies per question. Note: a cache hit still consumes the
    # caller's ai_quota (the route dependency runs first) — conservative and
    # intended; it does NOT consume Claude budget, so cached answers keep
    # working even after the daily spend breaker trips.
    qhash = _question_hash(question)
    version = index_version()
    cached = db.get_meta_answer(qhash, version)
    if cached is not None:
        return cached

    candidates, best_dense = _retrieve(question)

    if not candidates or (best_dense is not None and best_dense > DISTANCE_FLOOR):
        # Two-tier fallback: nothing in the corpus is close enough to help, so
        # don't inject misleading chunks — answer from model knowledge with an
        # explicit preface instead of stonewalling the user.
        answer = claude_service.ask_claude(
            f"Question: {question}",
            system=_system_prompt(META_FALLBACK_SYSTEM_PROMPT),
        )
        result = {"answer": answer, "sources": [], "corpus_vintage": corpus_vintage()}
        db.put_meta_answer(qhash, version, result)
        return result

    context_blocks, sources = [], []
    src_index: dict[tuple, int] = {}
    block_to_source: list[int] = []
    for candidate in candidates:
        doc, meta = candidate["document"], candidate["metadata"]
        source = meta.get("source", "unknown")
        section = meta.get("section", "unknown")
        text = _strip_context_header(doc, source, section)
        context_blocks.append(f"[{len(context_blocks) + 1}] [{source} — {section}]\n{text}")
        key = (source, section)
        if key not in src_index:
            src_index[key] = len(sources)
            sources.append({
                "source": source,
                "section": section,
                "snippet": text[:200].strip(),
            })
        block_to_source.append(src_index[key])

    context = "\n\n---\n\n".join(context_blocks)
    prompt = f"""Context from the Valorant knowledge base (numbered blocks):

{context}

Question: {question}

Respond as JSON: "answer" is your answer text (following the system prompt's style \
rules), and "used_sources" lists the numbers of the context blocks your answer \
actually drew on (empty list if none were relevant)."""

    message = claude_service._create(
        model=claude_service.CLAUDE_MODEL,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": META_ANSWER_SCHEMA}},
        system=_system_prompt(META_SYSTEM_PROMPT),
        messages=[{"role": "user", "content": prompt}],
    )
    text = next((block.text for block in message.content if block.type == "text"), "")
    if not text and message.stop_reason == "max_tokens":
        raise RuntimeError("Claude hit the token limit before producing text")

    try:
        parsed = json.loads(text)
        answer = parsed["answer"]
        if not isinstance(answer, str):
            raise TypeError("answer is not a string")
        used_blocks = {int(n) for n in parsed.get("used_sources", [])}
        used_sources = {
            block_to_source[n - 1] for n in used_blocks if 1 <= n <= len(block_to_source)
        }
        for idx, entry in enumerate(sources):
            entry["used"] = idx in used_sources
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        # Parse fallback: a malformed structured response degrades to the raw
        # text with retrieval-ordered sources and no used flags (the `used`
        # field is optional in the response contract) instead of a 500.
        answer = text

    result = {"answer": answer, "sources": sources, "corpus_vintage": corpus_vintage()}
    db.put_meta_answer(qhash, version, result)
    return result
