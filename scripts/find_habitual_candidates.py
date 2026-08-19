"""Phase 1: Candidate Scanner for Habitual / Single-Category Buyers.
Scans all 15,000+ normalized reviews for scope restriction, non-exploration, trust, and price friction signals.
Outputs candidate counts and saves data/processed/habitual_candidates.json.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from src.config import PROCESSED_DIR
from src.ingestion.schema import NormalizedReview

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Patterns for Phase 1 Candidate Extraction (No capping applied)
PATTERNS = {
    "scope_restriction": re.compile(
        r"only buy|only use|only order|just buy|just order|stick to|never try|won't try|only for|only grocery|only milk|only snacks|single item|specific item|routine",
        re.IGNORECASE,
    ),
    "trust_and_awareness": re.compile(
        r"didn't know|unaware|don't explore|never explore|hard to find|search fail|cluttered|never browse|no variety|limited choice|catalog|find other|search results|trust issue|fake|authentic|scam|cheat|bad return|strict refund|no return|no cancellation|fraud|trust|doubt|cheating|fake offer|policy",
        re.IGNORECASE,
    ),
    "expiry_and_quality": re.compile(
        r"expiry|expiration|expiry date|near expiry|expired|spoiled|stale|rotten|foul smell|bad egg|damaged food|freshness|quality issue|fungus|fungal",
        re.IGNORECASE,
    ),
    "price_and_fees": re.compile(
        r"cheaper on|expensive|costly|handling fee|platform fee|delivery charge|delivery fee|price comparison|amazon|bigbasket|blinkit|instamart|flipkart",
        re.IGNORECASE,
    ),
    "sos_emergency": re.compile(
        r"emergency|urgent|sos|medicine|pharmacy|cough|fever|medical|injury|band-aid|guest|guests|cooking gap|need quickly|last minute",
        re.IGNORECASE,
    ),
}


def scan_candidates() -> dict[str, Any]:
    in_file = PROCESSED_DIR / "normalized_reviews.json"
    if not in_file.exists():
        logger.error("Normalized reviews file not found at %s", in_file)
        return {}

    raw_data = json.loads(in_file.read_text(encoding="utf-8"))
    reviews = [NormalizedReview.from_dict(r) for r in raw_data]
    total_reviews = len(reviews)
    logger.info("Scanning all %d normalized reviews for habitual buyer signals...", total_reviews)

    candidates: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {k: 0 for k in PATTERNS}

    for r in reviews:
        matches = {k: bool(pat.search(r.body)) for k, pat in PATTERNS.items()}
        # Include review if it matches scope_restriction OR at least one of the 4 friction barriers
        if any(matches.values()):
            for k, hit in matches.items():
                if hit:
                    category_counts[k] += 1

            candidates.append({
                "review_id": r.review_id,
                "rating": r.rating,
                "date": r.date,
                "app_version": r.app_version,
                "body": r.body,
                "platform": r.platform,
                "thumbs_up": r.thumbs_up,
                "signals": matches,
            })

    out_file = PROCESSED_DIR / "habitual_candidates.json"
    out_file.write_text(json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 60)
    print(" 📊 PHASE 1: HABITUAL BUYER CANDIDATE SCAN RESULTS")
    print("=" * 60)
    print(f" Total Corpus Reviews Scanned:  {total_reviews:,}")
    print(f" Relevant Candidates Extracted:  {len(candidates):,} ({100 * len(candidates) / total_reviews:.1f}% of total corpus)")
    print("-" * 60)
    print(" Signal Distribution Breakdown:")
    for k, cnt in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"   • {k.replace('_', ' ').title():<24}: {cnt:>5,} reviews ({100 * cnt / total_reviews:.1f}%)")
    print("-" * 60)
    print(f" Saved full un-capped candidate dataset to:\n   👉 {out_file.resolve()}")
    print("=" * 60 + "\n")

    return {
        "total_reviews": total_reviews,
        "candidate_count": len(candidates),
        "category_counts": category_counts,
        "out_file": str(out_file),
    }


if __name__ == "__main__":
    scan_candidates()
