"""Operational runner for multi-stage refresh pipelines (ingest -> embed -> analyze)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.config import PROCESSED_DIR, PROJECT_ROOT, VECTOR_STORE_DIR
from src.ingestion.run import run_ingestion
from src.embeddings.run import run_embed_all
from src.analysis.run import main as run_core_analysis
from src.analysis.run_segmentation import run_segmentation_pipeline
from src.analysis.run_user_needs import run_user_needs_pipeline
from src.analysis.run_multi_category import run_multi_category_pipeline

logger = logging.getLogger(__name__)


def run_refresh_pipeline(
    incremental: bool = True,
    lookback_weeks: int = 10,
    rule_baseline: bool = False,
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

    logger.info("=== STAGE 3: Core & Segment Analysis Pipelines ===")
    analysis_args = ["--input", str(in_path), "--output-dir", str(out_dir)]
    if rule_baseline:
        analysis_args.append("--rule-baseline")
    
    code = run_core_analysis(analysis_args)
    if code != 0:
        logger.error("Core analysis stage failed with exit code %d", code)
        return code

    logger.info("Running Customer Segmentation pipeline...")
    run_segmentation_pipeline(reviews_file=in_path, output_dir=out_dir)

    logger.info("Running User Needs Grievances pipeline...")
    run_user_needs_pipeline(reviews_file=in_path, output_dir=out_dir)

    logger.info("Running Multi-Category Shopper pipeline...")
    run_multi_category_pipeline(reviews_file=in_path, output_dir=out_dir)

    logger.info("=== REFRESH PIPELINE COMPLETED SUCCESSFULLY ===")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Myntra Operational Orchestrator")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    refresh_parser = subparsers.add_parser("refresh", help="Run full refresh pipeline: ingest -> embed -> analyze")
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
    refresh_parser.add_argument(
        "--rule-baseline",
        action="store_true",
        help="Force rule-based keyword analysis (skips Groq API calls)",
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
            rule_baseline=args.rule_baseline,
        )
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
