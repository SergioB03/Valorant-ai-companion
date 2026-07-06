import threading
from pathlib import Path
from app.services.claude_service import ask_claude

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
CHROMA_DIR = DATA_DIR / "chroma_db"
COLLECTION_NAME = "valorant_knowledge"

MIN_CHUNK_CHARS = 200
MAX_CHUNK_CHARS = 1200

_client = None
_collection = None
_lock = threading.RLock()

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
        while len(piece) > limit:
            out.append(piece[:limit])
            piece = piece[limit:]
        out.append(piece)
    return [p.strip() for p in out if p.strip()]

def chunk_markdown(text: str, source: str) -> list[dict]:
    sections = []
    heading, lines = source, []
    for line in text.splitlines():
        if line.startswith("## "):
            if lines:
                sections.append((heading, "\n".join(lines).strip()))
            heading = line[3:].strip()
            lines = [line]
        else:
            lines.append(line)
    if lines:
        sections.append((heading, "\n".join(lines).strip()))

    raw = []
    for heading, body in sections:
        if not body:
            continue
        for piece in _split_long(body, MAX_CHUNK_CHARS):
            raw.append({"section": heading, "text": piece})

    merged = []
    for chunk in raw:
        if (
            merged
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

def _ingest(collection) -> dict:
    files = _knowledge_files()
    ids, documents, metadatas = [], [], []
    for path in files:
        for chunk in chunk_markdown(path.read_text(encoding="utf-8"), path.name):
            ids.append(chunk["id"])
            documents.append(chunk["text"])
            metadatas.append(chunk["metadata"])
    if ids:
        collection.add(ids=ids, documents=documents, metadatas=metadatas)
    return {"documents": len(files), "chunks": len(ids)}

def ensure_index() -> dict:
    with _lock:
        collection = _get_collection()
        if collection.count() == 0:
            return _ingest(collection)
        return {"documents": len(_knowledge_files()), "chunks": collection.count()}

def reindex() -> dict:
    global _client, _collection
    with _lock:
        import chromadb
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        try:
            _client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        _collection = _client.get_or_create_collection(COLLECTION_NAME)
        return _ingest(_collection)

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

def status() -> dict:
    documents = len(_knowledge_files())
    if not is_available():
        return {"ready": False, "documents": documents, "chunks": 0}
    chunks = _get_collection().count()
    return {"ready": chunks > 0, "documents": documents, "chunks": chunks}

META_SYSTEM_PROMPT = (
    "You are a Valorant knowledge assistant. Answer the question using ONLY the "
    "provided context. If the context does not cover the question, say so clearly "
    "and note that your information may be outdated. Cite the sections you used "
    "(by their source file and section name). Be concise and practical. "
    "Plain text only — no markdown headers, asterisks, or bullet syntax. Use short "
    "paragraphs and numbered lines like '1.' at most."
)

def _query(question: str, n_results: int = 5) -> dict:
    with _lock:
        collection = _get_collection()
        return collection.query(query_texts=[question], n_results=n_results)

def ask_meta(question: str) -> dict:
    results = _query(question)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    context_blocks, sources, seen = [], [], set()
    for doc, meta in zip(documents, metadatas):
        source = meta.get("source", "unknown")
        section = meta.get("section", "unknown")
        context_blocks.append(f"[{source} — {section}]\n{doc}")
        key = (source, section)
        if key not in seen:
            seen.add(key)
            sources.append({
                "source": source,
                "section": section,
                "snippet": doc[:200].strip(),
            })

    context = "\n\n---\n\n".join(context_blocks)
    prompt = f"""Context from the Valorant knowledge base:

{context}

Question: {question}"""

    answer = ask_claude(prompt, system=META_SYSTEM_PROMPT)
    return {"answer": answer, "sources": sources}
