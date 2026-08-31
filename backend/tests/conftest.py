"""Shared test setup.

ChromaDB is a heavy optional dependency that only the RAG feature needs, and
importing app.main pulls it in transitively via app.routes.meta. Stubbing it
keeps the suite installable and fast (seconds, not minutes) without weakening
what is under test here -- none of these tests exercise retrieval.
"""

import os
import sys
from unittest.mock import MagicMock

sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("chromadb.config", MagicMock())
sys.modules.setdefault("chromadb.utils", MagicMock())
sys.modules.setdefault("chromadb.utils.embedding_functions", MagicMock())

# A known-good configuration, so a developer's real .env cannot change results.
os.environ.setdefault("CORS_ORIGINS", "https://rebuy.gg")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")
os.environ.setdefault("RIOT_API_KEY", "HDEV-test-not-a-real-key")
