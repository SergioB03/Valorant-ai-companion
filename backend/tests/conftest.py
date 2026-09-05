"""Shared test setup.

ChromaDB is a heavy optional dependency that only the RAG feature needs, and
importing app.main pulls it in transitively via app.routes.meta. Stubbing it
keeps the suite installable and fast (seconds, not minutes) without weakening
what is under test here -- none of these tests exercise retrieval.
"""

import os
import sys
from unittest.mock import MagicMock

import dotenv

# Neutralise load_dotenv before any app module imports.
#
# riot_service and main call load_dotenv() at import, which reads the real
# backend/.env. That makes the suite non-hermetic -- results depend on whatever
# a developer happens to have configured -- and it pulled a live API key into
# an assertion failure message, which is exactly how a secret ends up in a CI
# log. Tests supply their own values below.
dotenv.load_dotenv = lambda *args, **kwargs: False

sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("chromadb.config", MagicMock())
sys.modules.setdefault("chromadb.utils", MagicMock())
sys.modules.setdefault("chromadb.utils.embedding_functions", MagicMock())

# A known-good configuration. Set unconditionally, not via setdefault, so an
# exported shell variable cannot change results either.
os.environ["CORS_ORIGINS"] = "https://rebuy.gg"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-not-a-real-key"
os.environ["HENRIK_API_KEY"] = "HDEV-test-not-a-real-key"
os.environ.pop("RIOT_API_KEY", None)
os.environ.pop("ADMIN_TOKEN", None)
