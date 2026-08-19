from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.ingestion.fetch import fetch_all, save_raw_snapshot
from src.ingestion.normalize import date_range, normalize_reviews
from src.ingestion.schema import NormalizedReview
from src.config import PROCESSED_DIR, DATA_DIR, LOOKBACK_WEEKS, MIN_WORD_COUNT

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROCESSED_DIR / "normalized_reviews.json"
DEFAULT_RAW_SNAPSHOT = DATA_DIR / "raw" / "raw_reviews_snapshot.json"


def _merge_stats(*counters: Counter[str]) -> Counter[str]:
    merged: Counter[str] = Counter()
    for counter in counters:
        merged.update(counter)
    return merged


def _load_existing(output_path: Path) -> list[NormalizedReview]:
    """Load the previously saved corpus, tolerating a missing/corrupt file."""
    if not output_path.exists():
        return []
    try:
        data = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[NormalizedReview] = []
    for row in data if isinstance(data, list) else []:
        if isinstance(row, dict):
            try:
                out.append(NormalizedReview.from_dict(row))
            except (KeyError, TypeError, ValueError):
                continue
    return out


def run_ingestion(
    output_path: Path | None = None,
    lookback_weeks: int | None = None,
    min_word_count: int | None = None,
    save_raw: bool = False,
    incremental: bool = True,
    overlap_days: int | None = None,
    sources: list[str] | None = None,
) -> tuple[list[NormalizedReview], Counter[str]]:
    output_path = output_path or DEFAULT_OUTPUT
    min_words = min_word_count or MIN_WORD_COUNT
    weeks = lookback_weeks or LOOKBACK_WEEKS

    existing: list[NormalizedReview] = []
    since: datetime | None = None
    if incremental:
        overlap = overlap_days if overlap_days is not None else 3
        existing = _load_existing(output_path)
        _, latest = date_range(existing)
        if latest:
            try:
                since = datetime.fromisoformat(latest).replace(tzinfo=timezone.utc) - timedelta(
                    days=max(overlap, 0)
                )
            except ValueError:
                since = None

    if since is not None:
        # For incremental, calculate lookback based on since date
        delta = datetime.now(timezone.utc) - since
        calc_weeks = max(int(delta.days / 7) + 1, 1)
        raw_reviews, fetch_stats = fetch_all(lookback_weeks=calc_weeks, sources=sources)
    else:
        raw_reviews, fetch_stats = fetch_all(lookback_weeks=weeks, sources=sources)

    if save_raw:
        save_raw_snapshot(raw_reviews, str(DEFAULT_RAW_SNAPSHOT))

    normalized_new, norm_stats = normalize_reviews(raw_reviews, min_word_count=min_words)

    if existing:
        merged: dict[str, NormalizedReview] = {r.review_id: r for r in existing}
        added = 0
        for review in normalized_new:
            if review.review_id not in merged:
                added += 1
            merged[review.review_id] = review
        normalized = sorted(merged.values(), key=lambda r: r.date)
        norm_stats["existing_count"] = len(existing)
        norm_stats["newly_added"] = added
    else:
        normalized = normalized_new

    stats = _merge_stats(fetch_stats, norm_stats)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [review.to_dict() for review in normalized]
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    min_date, max_date = date_range(normalized)
    stats["date_min"] = min_date or ""
    stats["date_max"] = max_date or ""

    return normalized, stats


def print_report(stats: Counter[str], output_path: Path) -> None:
    print("\n=== Ingestion Report ===")
    print(f"Output: {output_path}")
    print(f"Raw Google Play:       {stats.get('raw_google_play', 0)}")
    print(f"Raw App Store:         {stats.get('raw_app_store', 0)}")
    print(f"Raw Reddit:            {stats.get('raw_reddit', 0)}")
    print(f"Raw X (Twitter):       {stats.get('raw_x', 0)}")
    print(f"Raw YouTube:           {stats.get('raw_youtube', 0)}")
    print(f"Total Raw Fetched:     {stats.get('total_raw_fetched', 0)}")
    print(f"Dropped (too short):   {stats.get('dropped_too_short', 0)}")
    print(f"Dropped (emoji-only):  {stats.get('dropped_emoji_only', 0)}")
    print(f"Dropped (non-English): {stats.get('dropped_non_english', 0)}")
    print(f"Dropped (duplicate):   {stats.get('dropped_duplicate', 0)}")
    print(f"Normalized (new fetch):{stats.get('normalized_count', 0)}")
    if "existing_count" in stats:
        print(f"Existing corpus:       {stats.get('existing_count', 0)}")
        print(f"Newly added (merged):  {stats.get('newly_added', 0)}")
    print(f"Date range:            {stats.get('date_min')} -> {stats.get('date_max')}")
    print("========================\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest and normalize reviews/discussions.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path for normalized_reviews.json",
    )
    parser.add_argument(
        "--lookback-weeks",
        type=int,
        default=None,
        help="Weeks of reviews to fetch on a full build",
    )
    parser.add_argument(
        "--full-build",
        action="store_true",
        help="Perform a full rebuild (overwrite) instead of default incremental run",
    )
    parser.add_argument(
        "--min-word-count",
        type=int,
        default=None,
        help="Minimum word count for review body",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default=None,
        help="Comma-separated list of active sources (e.g. reddit,youtube)",
    )
    parser.add_argument(
        "--save-raw",
        action="store_true",
        help="Save raw fetched reviews to snapshots",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    sources_list = [s.strip() for s in args.sources.split(",")] if args.sources else None
    try:
        reviews_list, stats = run_ingestion(
            output_path=args.output,
            lookback_weeks=args.lookback_weeks,
            min_word_count=args.min_word_count,
            save_raw=args.save_raw,
            incremental=not args.full_build,
            sources=sources_list,
        )
    except Exception as exc:
        logging.error("Ingestion failed: %s", exc)
        return 1

    print_report(stats, args.output)

    if not reviews_list:
        logging.error("No reviews normalized — check raw data, or filters.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
