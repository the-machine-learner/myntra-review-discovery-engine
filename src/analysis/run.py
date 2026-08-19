"""CLI entrypoint for running the analysis pipeline."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.analysis.pipeline import run_pipeline, save_artifacts
from src.analysis.rule_baseline import run_rule_baseline
from src.config import PROCESSED_DIR, PROJECT_ROOT
from src.embeddings.run import load_reviews

DEFAULT_REVIEWS_PATH = PROCESSED_DIR / "normalized_reviews.json"
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    
    parser = argparse.ArgumentParser(description="Run VOC review analysis (Groq or rule-based baseline).")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_REVIEWS_PATH,
        help="Path to normalized_reviews.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROCESSED_DIR,
        help="Directory to save themes.json and unmet_needs.json",
    )
    parser.add_argument(
        "--rule-baseline",
        action="store_true",
        help="Force run the rule-based keyword fallback (skips Groq API)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for stratified sampling",
    )
    parser.add_argument(
        "--sample-cap",
        type=int,
        default=None,
        help="Override maximum reviews to sample for analysis",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if not args.input.exists():
        logging.error("Input reviews file not found: %s. Run ingestion first.", args.input)
        return 1

    try:
        reviews = load_reviews(args.input)
    except Exception as exc:
        logging.error("Failed to load reviews from %s: %s", args.input, exc)
        return 1

    has_api_key = bool(os.getenv("GROQ_API_KEY"))
    run_baseline = args.rule_baseline or not has_api_key

    if run_baseline:
        if not has_api_key:
            logger.info("GROQ_API_KEY not found in environment. Running offline rule-based baseline...")
        else:
            logger.info("Rule-based baseline forced. Running offline keyword clustering...")
        try:
            result = run_rule_baseline(reviews, seed=args.seed, sample_cap=args.sample_cap)
        except Exception as exc:
            logging.error("Rule-based baseline analysis failed: %s", exc)
            return 1
    else:
        logger.info("Running Groq-powered LLM analysis pipeline...")
        try:
            result = run_pipeline(reviews, seed=args.seed, sample_cap=args.sample_cap)
        except Exception as exc:
            logging.error("LLM-powered analysis failed: %s. Re-trying with Rule-based baseline...", exc)
            try:
                result = run_rule_baseline(reviews, seed=args.seed, sample_cap=args.sample_cap)
            except Exception as e_inner:
                logging.error("Fallback baseline analysis also failed: %s", e_inner)
                return 1

    try:
        save_artifacts(result, args.output_dir)
        logger.info("Analysis artifacts successfully saved to %s", args.output_dir)
    except Exception as exc:
        logging.error("Failed to save analysis artifacts: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
