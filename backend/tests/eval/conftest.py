"""Eval-only test setup.

The suite-wide conftest (tests/conftest.py) stubs chromadb with a MagicMock so
the fast unit suite never pays for the native dependency. The retrieval eval is
the one place that needs the REAL index, so when the eval is explicitly enabled
(RUN_RAG_EVAL=1) this conftest removes those stubs again before any test module
imports rag_service — rag_service imports chromadb lazily inside functions, so
un-stubbing here is sufficient.

Run the eval only as `pytest tests/eval` (see test_rag_eval.py's docstring for
the exact command); running the whole suite with RUN_RAG_EVAL=1 would un-stub
chromadb for the unit tests too, which merely makes them slower, not wrong.
"""

import os
import sys
from unittest.mock import MagicMock


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "eval: slow retrieval-quality eval against the real Chroma index "
        "(opt in with RUN_RAG_EVAL=1; excluded from the default suite by skipif)",
    )


if os.getenv("RUN_RAG_EVAL") == "1":
    for name in [n for n in list(sys.modules) if n == "chromadb" or n.startswith("chromadb.")]:
        if isinstance(sys.modules[name], MagicMock):
            del sys.modules[name]
