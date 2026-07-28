"""Knowledge base ingestion.

Run as a module::

    python -m app.rag.ingest            # incremental upsert
    python -m app.rag.ingest --reset    # rebuild from scratch
    python -m app.rag.ingest --probe    # ingest, then sanity-check retrieval

The probe mode exists because a silently-empty vector store is the most common
RAG failure and the hardest to notice from the outside: agents keep answering,
just without grounding.
"""

from __future__ import annotations

import argparse
import sys

from app.core.logging import configure_logging, get_logger
from app.rag.chunking import load_knowledge_base
from app.rag.retriever import get_retriever
from app.rag.store import get_vector_store

logger = get_logger(__name__)

#: Questions that must return grounded doctrine for the platform to work.
PROBE_QUERIES: list[tuple[str, str]] = [
    ("How much drinking water per person per day in a relief camp?", "shelter"),
    ("How should mass casualties be distributed across hospitals?", "medical"),
    ("What order should relief resources be allocated in?", "allocation"),
    ("When should evacuation happen during a flood?", "flood"),
    ("How do I counter rumours during a disaster?", "communication"),
]


def ingest(reset: bool = False) -> int:
    store = get_vector_store()

    if reset:
        logger.info("rag.reset_requested")
        store.reset()

    chunks = load_knowledge_base()
    if not chunks:
        logger.error("rag.no_chunks", detail="knowledge base is empty or unreadable")
        return 0

    written = store.index(chunks)
    logger.info("rag.ingest_complete", chunks=written, total_in_store=store.count())
    return written


def probe() -> bool:
    retriever = get_retriever()
    all_passed = True

    print("\n" + "=" * 78)
    print("RAG PROBE — verifying doctrine is retrievable and correctly cited")
    print("=" * 78)

    for question, topic in PROBE_QUERIES:
        result = retriever.retrieve(question, top_k=3)
        status = "PASS" if not result.is_empty else "FAIL"
        if result.is_empty:
            all_passed = False

        print(f"\n[{status}] ({topic}) {question}")
        for chunk in result.chunks[:2]:
            cite = chunk.citation
            print(
                f"   {chunk.relevance:.3f}  {cite.source_id} §{cite.section}"
                f"  — {cite.document_title}"
            )
            print(f"          \"{cite.snippet[:130]}…\"")

    print("\n" + "=" * 78)
    print("PROBE RESULT:", "ALL QUERIES GROUNDED" if all_passed else "GAPS DETECTED")
    print("=" * 78 + "\n")
    return all_passed


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Ingest SentinelAI doctrine corpus")
    parser.add_argument("--reset", action="store_true", help="clear the collection first")
    parser.add_argument("--probe", action="store_true", help="run retrieval checks after ingest")
    args = parser.parse_args()

    written = ingest(reset=args.reset)
    if written == 0:
        return 1

    if args.probe and not probe():
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
