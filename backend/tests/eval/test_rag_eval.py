"""Gold-set retrieval eval — Hit@5 / MRR@5 against the REAL Chroma index.

Excluded from the default suite: tests/conftest.py stubs chromadb (this eval
would measure a MagicMock), and building the index needs the MiniLM embedding
model (~80 MB, cached under ~/.cache/chroma after the first run). Opt in
explicitly:

    # Git Bash, from backend/
    RUN_RAG_EVAL=1 venv/Scripts/python.exe -m pytest tests/eval -q -s

    # PowerShell, from backend/
    $env:RUN_RAG_EVAL='1'; venv/Scripts/python.exe -m pytest tests/eval -q -s

The session fixture REBUILDS backend/data/chroma_db from the working-tree corpus
so the numbers always measure the current chunker + knowledge files (the dev
index is left in that freshly-built state, which is also what a deploy bakes).

In CI, cache ~/.cache/chroma (actions/cache) or the model re-download makes this
the slowest step in the pipeline. Zero Claude calls — retrieval only, no spend.

Metrics:
  - Hit@5 (section): a top-5 chunk matches an expected (source, section) pair.
    This is the honest headline number — it is what the citation chips show.
  - Hit@5 (source):  a top-5 chunk comes from an expected source file at all.
  - MRR@5: mean reciprocal rank of the first section-level match.
The wave-4 gate in docs/OPTIMIZATION-PLAN.md (RA8) reads Hit@5 (section);
the measured gate decision is written up there and in
docs/changes/2026-09-05-optimization-waves/README.md.
"""

import json
import os
from pathlib import Path

import pytest

RUN = os.getenv("RUN_RAG_EVAL") == "1"

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not RUN, reason="retrieval eval needs the real Chroma index; opt in with RUN_RAG_EVAL=1"
    ),
]

GOLD_PATH = Path(__file__).parent / "gold_set.json"
K = 5  # headline metrics are @5 for comparability even though prod retrieves more

# Regression floors (see module docstring). Measured history, 2026-09-05:
#   baseline (old chunker, 31 positives):      section=0.871 source=1.000 MRR@5=0.745
#   + chunker fixes/headers/ingestion (34 q):  section=0.941 source=0.971 MRR@5=0.848
#   + BM25 hybrid w/ RRF (final tree):         section=1.000 source=1.000 MRR@5=0.794
# (the hybrid trades a little MRR for closing both remaining lexical misses —
# everything gold now reaches the 8-chunk context window, which is what the
# answer actually sees). Floors sit under the final numbers with headroom for
# future corpus growth; loosen only with a written justification here.
HIT5_SECTION_FLOOR = 0.90
HIT5_SOURCE_FLOOR = 0.95
MRR5_FLOOR = 0.70


def _load_gold():
    data = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    positives = [q for q in data["questions"] if q["type"] == "positive"]
    negatives = [q for q in data["questions"] if q["type"].startswith("negative")]
    return positives, negatives


@pytest.fixture(scope="session")
def rag():
    """Real rag_service over a freshly built index of the working-tree corpus."""
    from app.services import rag_service

    assert rag_service.is_available(), "chromadb must be importable for the eval"
    # Earlier unit tests (or the suite conftest) may have primed module state
    # with a stubbed client — drop it so the PersistentClient is the real one.
    rag_service._client = None
    rag_service._collection = None
    info = rag_service.reindex()
    assert info["chunks"] > 0, "reindex produced an empty collection"
    print(f"\n[eval] index built: {info['documents']} documents, {info['chunks']} chunks")
    return rag_service


def _top_hits(rag_service, question: str, k: int):
    """[(source, section, dense_distance|None), ...] via the PRODUCT retrieval
    path (_retrieve: hybrid dense+BM25, RRF-fused) — the eval must measure what
    /meta/ask actually uses. distance is None for chunks only BM25 surfaced."""
    candidates, _ = rag_service._retrieve(question, n_results=k)
    return [
        (c["metadata"].get("source"), c["metadata"].get("section"), c["distance"])
        for c in candidates
    ]


def _best_dense(rag_service, question: str):
    """Best dense distance — what the two-tier DISTANCE_FLOOR actually compares."""
    return rag_service._retrieve(question, n_results=1)[1]


def _fmt_d(dist) -> str:
    return f"{dist:.3f}" if dist is not None else "bm25"


def _matches(hit, expect) -> bool:
    source, section, _ = hit
    for exp_source, exp_section in expect:
        if source == exp_source and (exp_section == "*" or section == exp_section):
            return True
    return False


def test_positive_retrieval(rag):
    positives, _ = _load_gold()
    assert len(positives) >= 20, "gold set thinned out — keep it meaningful"

    section_hits = source_hits = 0
    rr_total = 0.0
    misses = []
    print(f"\n[eval] positive questions: {len(positives)} (metrics @ k={K})")
    for q in positives:
        hits = _top_hits(rag, q["question"], K)
        sec_rank = next((i + 1 for i, h in enumerate(hits) if _matches(h, q["expect"])), None)
        src_rank = next(
            (i + 1 for i, h in enumerate(hits) if any(h[0] == e[0] for e in q["expect"])),
            None,
        )
        if sec_rank:
            section_hits += 1
            rr_total += 1.0 / sec_rank
        if src_rank:
            source_hits += 1
        top = hits[0] if hits else ("-", "-", None)
        flag = " " if sec_rank else ("~" if src_rank else "!")
        print(
            f"  {flag} {q['id']:<22} sec_rank={sec_rank or '-':<2} src_rank={src_rank or '-':<2}"
            f" top1=({top[0]} > {top[1]}, d={_fmt_d(top[2])})"
        )
        if not sec_rank:
            misses.append((q["id"], "section", top))

    n = len(positives)
    hit5_section = section_hits / n
    hit5_source = source_hits / n
    mrr5 = rr_total / n
    print(
        f"[eval] Hit@{K} section={hit5_section:.3f} ({section_hits}/{n})  "
        f"source={hit5_source:.3f} ({source_hits}/{n})  MRR@{K}={mrr5:.3f}"
    )
    if misses:
        print(f"[eval] section-level misses: {[m[0] for m in misses]}")

    assert hit5_section >= HIT5_SECTION_FLOOR, f"Hit@{K} (section) regressed: {hit5_section:.3f}"
    assert hit5_source >= HIT5_SOURCE_FLOOR, f"Hit@{K} (source) regressed: {hit5_source:.3f}"
    assert mrr5 >= MRR5_FLOOR, f"MRR@{K} regressed: {mrr5:.3f}"


def test_negative_probes_and_distance_floor(rag):
    """Measure where out-of-corpus questions land, and pin the two-tier floor.

    far-domain probes MUST sit above rag_service.DISTANCE_FLOOR (they get the
    "outside my notes" path); every positive's best hit MUST sit below it (no
    legitimate question gets floored). near-domain probes are asserted on
    nothing — measurement shows they score closer than some legitimate hits
    (wrong-game vocabulary overlaps), which is exactly why the floor alone
    cannot catch them and the prompt has to; the print keeps that visible.
    """
    positives, negatives = _load_gold()
    far = [q for q in negatives if q["type"] == "negative_far"]
    near = [q for q in negatives if q["type"] == "negative_near"]
    assert len(negatives) >= 5, "keep at least 5 negative probes in the gold set"

    pos_best = {q["id"]: _best_dense(rag, q["question"]) for q in positives}
    far_best = {q["id"]: _best_dense(rag, q["question"]) for q in far}
    near_best = {q["id"]: _best_dense(rag, q["question"]) for q in near}

    print("\n[eval] best-hit distances (higher = further from the corpus):")
    print(f"  positives:   max={max(pos_best.values()):.3f} "
          f"(worst: {max(pos_best, key=pos_best.get)})")
    for qid, d in sorted(near_best.items(), key=lambda kv: kv[1]):
        print(f"  near-domain: {qid:<18} {d:.3f}  (floor cannot catch — prompt handles)")
    for qid, d in sorted(far_best.items(), key=lambda kv: kv[1]):
        print(f"  far-domain:  {qid:<18} {d:.3f}")

    from app.services import rag_service

    floor = getattr(rag_service, "DISTANCE_FLOOR", None)
    if floor is None:
        pytest.skip("rag_service.DISTANCE_FLOOR not shipped yet — distances measured above")

    print(f"[eval] DISTANCE_FLOOR={floor}")
    floored_positives = [qid for qid, d in pos_best.items() if d > floor]
    assert not floored_positives, (
        f"legitimate questions above the floor (would be denied context): {floored_positives}"
    )
    unfloored_far = [qid for qid, d in far_best.items() if d <= floor]
    assert not unfloored_far, f"far-domain junk below the floor (would get context): {unfloored_far}"
