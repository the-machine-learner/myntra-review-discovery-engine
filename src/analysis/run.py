"""CLI: python -m src.analysis.run

Runs the opportunity-area analysis pipeline (rule-tag -> sample ->
LLM-synthesize -> score -> write artifacts).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.config import PROCESSED_DIR, PROJECT_ROOT
from src.analysis.taxonomy import TAXONOMY, MVP_AREA_IDS
from src.analysis.pipeline import run_analysis, estimate_run_cost, load_reviews

DEFAULT_REVIEWS_PATH = PROCESSED_DIR / "normalized_reviews.json"

logger = logging.getLogger(__name__)


def _resolve_area_ids(areas_arg: str | None) -> list[str]:
    if not areas_arg:
        return list(MVP_AREA_IDS)
    ids = [a.strip() for a in areas_arg.split(",") if a.strip()]
    if ids == ["all"]:
        return list(TAXONOMY.keys())
    unknown = [a for a in ids if a not in TAXONOMY]
    if unknown:
        raise SystemExit(f"Unknown area_id(s): {unknown}. Valid: {list(TAXONOMY.keys())}")
    return ids


def print_dry_run_report(estimate: dict, area_ids: list[str]) -> None:
    print("\n=== Budget Dry Run ===")
    print(f"Areas: {area_ids}")
    for area_id, info in estimate["per_area"].items():
        print(
            f"  {area_id}: sample={info['sample_size']} "
            f"needs_llm_tag={info['reviews_needing_llm_tag']} "
            f"est_calls={info['estimated_calls']} est_tokens={info['estimated_tokens']}"
        )
    print(f"TOTAL estimated calls:  {estimate['total_estimated_calls']}")
    print(f"TOTAL estimated tokens: {estimate['total_estimated_tokens']}")
    print("======================\n")
    print("No Groq calls were made. Re-run without --dry-run-budget to execute.")


def print_run_report(result: dict) -> None:
    meta = result["run_metadata"]
    print("\n=== Analysis Run Report ===")
    print(f"Run ID:              {meta['run_id']}")
    print(f"Prompt version:      {meta['prompt_version']}")
    print(f"Corpus size:         {meta['corpus_size_at_run']}")
    print(f"Areas run:           {meta['area_ids']}")
    print(f"Groq calls made:     {meta['groq_call_count']}")
    print(f"Est. tokens used:    {meta['estimated_tokens_used']}")
    print(f"Validation OK:       {meta['validation_ok']}")
    if meta["validation_errors"]:
        print(f"Validation errors:   {meta['validation_errors']}")
    print()
    for score in sorted(result["scores"], key=lambda s: s["signal_score"], reverse=True):
        print(
            f"  [{score['signal_score']:>5.1f}] {score['label']:<40} "
            f"reach={score['reach']['pct']}% impact={score['impact']['blended_impact_score']} "
            f"confidence={score['confidence']['confidence_score']} "
            f"feasible_wo_$={score['feasible_without_monetary_incentive']}"
        )
    print("============================\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run opportunity-area analysis.")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_REVIEWS_PATH,
        help="Path to normalized_reviews.json",
    )
    parser.add_argument(
        "--areas",
        type=str,
        default=None,
        help="Comma-separated area_ids to run (default: MVP 7). Use 'all' for all 14.",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Rule-only $0 dry run — no Groq calls, just reach stats.",
    )
    parser.add_argument(
        "--dry-run-budget",
        action="store_true",
        help="Print estimated call/token count before spending anything.",
    )
    parser.add_argument(
        "--sample-cap",
        type=int,
        default=None,
        help="Override OPPORTUNITY_SAMPLE_CAP_PER_AREA for this run.",
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
        logging.error("Input not found: %s (run ingestion first)", args.input)
        return 1

    area_ids = _resolve_area_ids(args.areas)

    try:
        if args.dry_run_budget:
            reviews = load_reviews(args.input)
            estimate = estimate_run_cost(reviews, area_ids, sample_cap=args.sample_cap)
            print_dry_run_report(estimate, area_ids)
            return 0

        result = run_analysis(
            args.input,
            area_ids=area_ids,
            skip_llm=args.skip_llm,
            sample_cap=args.sample_cap,
        )
        print_run_report(result)
        return 0 if result["run_metadata"]["validation_ok"] else 1
    except Exception:
        logging.exception("Analysis run failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
