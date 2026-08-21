# Backend image: FastAPI + ChromaDB.
# The ONNX embedding model *and* the RAG index are built into the image, so a fresh
# container answers /meta/ask immediately — no ~80 MB model download or re-embedding
# at boot, and the index always matches the knowledge files shipped with the code.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ANONYMIZED_TELEMETRY=False

RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=app:app app ./app
COPY --chown=app:app data/knowledge ./data/knowledge

# /app/state holds the SQLite file (mental profiles + analytics). docker-compose.yml
# mounts a persistent volume here and points VAC_STATE_DIR at it.
RUN mkdir -p /app/state /app/data/chroma_db && chown -R app:app /app
USER app

# Bake the embedding model + Chroma index. ANTHROPIC_API_KEY is a placeholder: importing
# the RAG service constructs the Anthropic client (which insists on a key) but nothing
# here calls Claude.
RUN ANTHROPIC_API_KEY=build-placeholder \
    python -c "from app.services.rag_service import ensure_index; print('rag index:', ensure_index())"

EXPOSE 8000
# ROOT_PATH (e.g. /api) is the prefix the reverse proxy strips; telling uvicorn keeps it
# in redirects and /docs links. Empty for local runs.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --root-path \"${ROOT_PATH:-}\""]
