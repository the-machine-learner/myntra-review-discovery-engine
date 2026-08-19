"""Verification script asserting vector store size matches or exceeds normalized reviews count."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import PROCESSED_DIR, VECTOR_STORE_DIR
from src.embeddings.store import ReviewVectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify_index")


def main() -> int:
    reviews_file = PROCESSED_DIR / "normalized_reviews.json"
    if not reviews_file.exists():
        logger.error("normalized_reviews.json missing at %s", reviews_file)
        return 1

    try:
        raw = json.loads(reviews_file.read_text(encoding="utf-8"))
        corpus_count = len(raw) if isinstance(raw, list) else 0
    except Exception as exc:
        logger.error("Failed to read normalized_reviews.json: %s", exc)
        return 1

    store = ReviewVectorStore(persist_dir=VECTOR_STORE_DIR)
    vector_count = store.count()

    logger.info("Corpus review count: %d", corpus_count)
    logger.info("Vector store count: %d", vector_count)

    if corpus_count == 0:
        logger.error("Corpus review count is 0!")
        return 1

    if vector_count < corpus_count:
        logger.error(
            "Vector count (%d) is LESS than corpus count (%d). Vector index out of sync!",
            vector_count,
            corpus_count,
        )
        return 1

    logger.info("Index verification SUCCESS: Vector store (%d) matches corpus (%d).", vector_count, corpus_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
