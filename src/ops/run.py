"""Operational runner for multi-stage refresh pipelines (ingest -> embed).

The analysis layer (theme/segmentation/user-needs/multi-category pipelines) was
removed pending a from-scratch redesign for the Myntra domain. This runner only
carries the corpus and vector index forward until that layer is rebuilt.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.config import PROCESSED_DIR, PROJECT_ROOT, VECTOR_STORE_DIR
from src.ingestion.run import run_ingestion
from src.embeddings.run import run_embed_all

logger = logging.getLogger(__name__)


def run_refresh_pipeline(
    incremental: bool = True,
    lookback_weeks: int = 10,
    reviews_path: Path | None = None,
    output_dir: Path | None = None,
) -> int:
    in_path = reviews_path or (PROCESSED_DIR / "normalized_reviews.json")
    out_dir = output_dir or PROCESSED_DIR

    logger.info("=== STAGE 1: Ingestion ===")
    logger.info("Running ingestion (incremental=%s, lookback_weeks=%d)...", incremental, lookback_weeks)
    reviews, stats = run_ingestion(
        output_path=in_path,
        lookback_weeks=lookback_weeks,
        incremental=incremental,
    )
    logger.info("Ingestion complete. Total corpus size: %d reviews.", len(reviews))

    logger.info("=== STAGE 2: Embedding & Vector Store Indexing ===")
    logger.info("Indexing embeddings into ChromaDB at %s...", VECTOR_STORE_DIR)
    embed_stats = run_embed_all(
        reviews_path=in_path,
        batch_size=128,
        persist_dir=VECTOR_STORE_DIR,
    )
    logger.info(
        "Embedding complete. Newly embedded: %d, Total vector count: %d",
        embed_stats.get("newly_embedded", 0),
        embed_stats.get("collection_count_after", 0),
    )

    logger.info("=== REFRESH PIPELINE COMPLETED (analysis stage pending redesign) ===")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Myntra Operational Orchestrator")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    refresh_parser = subparsers.add_parser("refresh", help="Run refresh pipeline: ingest -> embed")
    refresh_parser.add_argument(
        "--incremental",
        action="store_true",
        default=True,
        help="Fetch only reviews newer than existing corpus (default: True)",
    )
    refresh_parser.add_argument(
        "--full-build",
        action="store_false",
        dest="incremental",
        help="Perform a full historical build instead of incremental merge",
    )
    refresh_parser.add_argument(
        "--lookback-weeks",
        type=int,
        default=10,
        help="Lookback window in weeks for full build or initial sync",
    )
    refresh_parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.subcommand == "refresh":
        return run_refresh_pipeline(
            incremental=args.incremental,
            lookback_weeks=args.lookback_weeks,
        )
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
