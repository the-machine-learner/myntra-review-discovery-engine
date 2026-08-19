"""Smoke test script for verification of offline RAG retrieval & data integrity."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import PROCESSED_DIR
from src.rag.retriever import ReviewRetriever

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("smoke_test")


def main() -> int:
    reviews_file = PROCESSED_DIR / "normalized_reviews.json"
    if not reviews_file.exists():
        logger.error("normalized_reviews.json missing at %s", reviews_file)
        return 1

    logger.info("Initializing ReviewRetriever...")
    retriever = ReviewRetriever()
    count = retriever.corpus_size
    logger.info("Vector store count: %d", count)

    if count == 0:
        logger.error("Vector store is empty! Embedding stage failed or index is missing.")
        return 1

    # Perform a test retrieval query
    test_query = "Why do users buy milk and daily staples on Myntra?"
    logger.info("Testing retrieval query: '%s'", test_query)
    results = retriever.retrieve(test_query, top_k=3)

    if not results:
        logger.error("Retrieval returned 0 results!")
        return 1

    logger.info("Smoke test passed! Retrieved %d matching reviews.", len(results))
    for i, r in enumerate(results, start=1):
        logger.info("  [%d] Similarity: %.4f | Review ID: %s | Rating: %s", i, r.similarity, r.review_id, r.rating)

    return 0


if __name__ == "__main__":
    sys.exit(main())
