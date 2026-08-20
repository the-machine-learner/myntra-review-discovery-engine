"""Operational runner for multi-stage refresh pipelines.

Stage sequence:
  1. Ingestion            (unchanged)
  2. Embedding + indexing (extended — threads taxonomy tags through)
  3. Opportunity analysis (new, opt-in via --run-analysis — costs Groq tokens)

Cadence is deliberately decoupled given the token constraint: ingest+embed is
cheap/local and can run on the existing weekly_refresh.yml schedule; the
analysis stage is opt-in per run (or use --analysis-only to rerun scoring
without re-ingesting, e.g. while iterating on the taxonomy/prompts).
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
    run_analysis_stage: bool = False,
    analysis_only: bool = False,
    area_ids: list[str] | None = None,
    sources: list[str] | None = None,
) -> int:
    in_path = reviews_path or (PROCESSED_DIR / "normalized_reviews.json")
    out_dir = output_dir or PROCESSED_DIR

    if not analysis_only:
        logger.info("=== STAGE 1: Ingestion ===")
        logger.info(
            "Running ingestion (incremental=%s, lookback_weeks=%d, sources=%s)...",
            incremental, lookback_weeks, sources or "default",
        )
        reviews, stats = run_ingestion(
            output_path=in_path,
            lookback_weeks=lookback_weeks,
            incremental=incremental,
            sources=sources,
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
    else:
        logger.info("--analysis-only: skipping ingest/embed stages")

    if run_analysis_stage or analysis_only:
        logger.info("=== STAGE 3: Opportunity-Area Analysis ===")
        from src.analysis.pipeline import run_analysis

        result = run_analysis(in_path, area_ids=area_ids)
        meta = result["run_metadata"]
        logger.info(
            "Analysis complete. Groq calls: %d, est. tokens: %d, validation_ok: %s",
            meta["groq_call_count"], meta["estimated_tokens_used"], meta["validation_ok"],
        )
    else:
        logger.info("Analysis stage skipped (pass --run-analysis to include it, costs Groq tokens)")

    logger.info("=== REFRESH PIPELINE COMPLETED ===")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Myntra Operational Orchestrator")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    refresh_parser = subparsers.add_parser("refresh", help="Run refresh pipeline: ingest -> embed -> [analysis]")
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
        "--run-analysis",
        action="store_true",
        help="Also run the opportunity-area analysis stage (costs Groq tokens).",
    )
    refresh_parser.add_argument(
        "--analysis-only",
        action="store_true",
        help="Skip ingest/embed, only (re)run the analysis stage on the existing corpus.",
    )
    refresh_parser.add_argument(
        "--areas",
        type=str,
        default=None,
        help="Comma-separated area_ids for the analysis stage (default: MVP 7).",
    )
    refresh_parser.add_argument(
        "--sources",
        type=str,
        default=None,
        help="Comma-separated ingestion sources (default: google_play,app_store,x,youtube). "
        "mouthshut is opt-in — must be named explicitly.",
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
        area_ids = [a.strip() for a in args.areas.split(",") if a.strip()] if args.areas else None
        sources = [s.strip() for s in args.sources.split(",") if s.strip()] if args.sources else None
        return run_refresh_pipeline(
            incremental=args.incremental,
            lookback_weeks=args.lookback_weeks,
            run_analysis_stage=args.run_analysis,
            analysis_only=args.analysis_only,
            area_ids=area_ids,
            sources=sources,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
