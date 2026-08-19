"""CLI: embed normalized reviews into Chroma."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from src.config import PROCESSED_DIR, PROJECT_ROOT, VECTOR_STORE_DIR
from src.embeddings.local_embedder import LocalEmbedder
from src.embeddings.store import (
    CHECKPOINT_PATH,
    ReviewVectorStore,
    compose_document,
    content_hash,
)
from src.ingestion.schema import NormalizedReview

DEFAULT_REVIEWS_PATH = PROCESSED_DIR / "normalized_reviews.json"
DEFAULT_BATCH_SIZE = 128

logger = logging.getLogger(__name__)


def load_reviews(path: Path) -> list[NormalizedReview]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [NormalizedReview.from_dict(item) for item in raw]


def filter_pending(
    reviews: list[NormalizedReview],
    store: ReviewVectorStore,
) -> tuple[list[NormalizedReview], list[str], list[str], Counter[str]]:
    stats: Counter[str] = Counter()
    pending_reviews: list[NormalizedReview] = []
    pending_docs: list[str] = []
    pending_hashes: list[str] = []

    stored_hashes = store.stored_hashes()

    for review in reviews:
        doc = compose_document(review)
        doc_hash = content_hash(doc)
        if stored_hashes.get(review.review_id) != doc_hash:
            pending_reviews.append(review)
            pending_docs.append(doc)
            pending_hashes.append(doc_hash)
        else:
            stats["skipped_unchanged"] += 1

    stats["total_input"] = len(reviews)
    stats["pending_embed"] = len(pending_reviews)
    return pending_reviews, pending_docs, pending_hashes, stats


def run_embed_all(
    reviews_path: Path,
    batch_size: int,
    persist_dir: Path,
    limit: int | None = None,
) -> Counter[str]:
    reviews = load_reviews(reviews_path)
    if limit is not None:
        reviews = reviews[:limit]
    store = ReviewVectorStore(persist_dir=persist_dir)
    embedder = LocalEmbedder()

    pending_reviews, pending_docs, pending_hashes, stats = filter_pending(reviews, store)
    stats["embedding_backend"] = "local"
    stats["embedding_model"] = embedder.model_name
    stats["collection_count_before"] = store.count()

    if not pending_reviews:
        stats["newly_embedded"] = 0
        stats["embed_batches"] = 0
        stats["collection_count_after"] = store.count()
        store.save_checkpoint(dict(stats))
        return stats

    start = time.time()
    embedded_count = 0

    for batch_start in range(0, len(pending_docs), batch_size):
        batch_docs = pending_docs[batch_start : batch_start + batch_size]
        batch_revs = pending_reviews[batch_start : batch_start + batch_size]
        batch_hashes = pending_hashes[batch_start : batch_start + batch_size]

        batch_vectors = embedder.embed_texts(batch_docs)
        store.upsert_batch(batch_revs, batch_vectors, batch_docs, batch_hashes)
        embedded_count += len(batch_docs)

        stats["newly_embedded"] = embedded_count
        stats["embed_batches"] = embedder.api_call_count
        stats["collection_count_after"] = store.count()
        store.save_checkpoint(dict(stats))

        logger.info(
            "Embedded batch %s-%s (%s/%s pending)",
            batch_start + 1,
            batch_start + len(batch_docs),
            embedded_count,
            len(pending_reviews),
        )

    stats["duration_seconds"] = round(time.time() - start, 1)
    stats["embed_batches"] = embedder.api_call_count
    stats["collection_count_after"] = store.count()
    store.save_checkpoint(dict(stats))
    return stats


def run_query(query: str, n_results: int, persist_dir: Path) -> None:
    store = ReviewVectorStore(persist_dir=persist_dir)
    if store.count() == 0:
        raise RuntimeError(
            "Vector store is empty. Run `python -m src.embeddings.run` first."
        )

    embedder = LocalEmbedder()
    query_vector = embedder.embed_one(query)
    results = store.query(query_vector, n_results=n_results)

    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    print(f"\nQuery: {query}")
    print(f"Backend: local  |  Model: {embedder.model_name}\n")
    for rank, (review_id, doc, meta, dist) in enumerate(
        zip(ids, documents, metadatas, distances), start=1
    ):
        sim = store.distance_to_similarity(dist)
        rating = meta.get("rating", "?")
        date = meta.get("date", "?")
        platform = meta.get("platform", "?")
        snippet = (doc or "")[:200].replace("\n", " ")
        print(f"{rank}. review_id={review_id} similarity={sim:.4f} rating={rating} platform={platform} date={date}")
        print(f"   {snippet}\n")


def print_embed_report(stats: Counter[str], persist_dir: Path) -> None:
    print("\n=== Embedding Report ===")
    print(f"Vector store: {persist_dir}")
    print(f"Backend:               {stats.get('embedding_backend', 'n/a')}")
    print(f"Model:                 {stats.get('embedding_model', 'n/a')}")
    print(f"Total input reviews:   {stats.get('total_input', 0)}")
    print(f"Pending embed:         {stats.get('pending_embed', 0)}")
    print(f"Newly embedded:        {stats.get('newly_embedded', 0)}")
    print(f"Skipped (unchanged):     {stats.get('skipped_unchanged', 0)}")
    print(f"Embed batches:         {stats.get('embed_batches', 0)}")
    print(f"Collection count:      {stats.get('collection_count_after', stats.get('collection_count_before', 0))}")
    if stats.get("duration_seconds"):
        print(f"Duration (s):            {stats.get('duration_seconds')}")
    print(f"Checkpoint:            {CHECKPOINT_PATH}")
    print("========================\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Embed reviews into Chroma.")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_REVIEWS_PATH,
        help="Path to normalized_reviews.json",
    )
    parser.add_argument(
        "--persist-dir",
        type=Path,
        default=VECTOR_STORE_DIR,
        help="Chroma persistence directory",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Texts per batch request",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Run retrieval sanity check for this query",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Results for --query mode",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Embed only the first N reviews (for testing)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if not args.input.exists():
        logging.error("Input not found: %s (run Phase 1 first)", args.input)
        return 1

    try:
        if args.query:
            run_query(args.query, args.top_k, args.persist_dir)
            return 0

        stats = run_embed_all(args.input, args.batch_size, args.persist_dir, args.limit)
        print_embed_report(stats, args.persist_dir)
        return 0
    except Exception as exc:
        logging.exception("Embedding failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
