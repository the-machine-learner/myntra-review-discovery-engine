"""Pipeline 1: Customer Segmentation Analysis over all normalized reviews."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.config import PROCESSED_DIR
from src.ingestion.schema import NormalizedReview
from src.analysis.sampler import segment_hints, rating_tier, SEGMENT_PATTERNS
from src.analysis.pipeline import stage_d_segments, _infer_segment

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SEGMENT_DESCRIPTIONS = {
    "habitual_trust_and_awareness_hesitant": "Habitual Shoppers (App Trust & Awareness Hesitant): Buys routine staples but hesitates on new categories due to lack of awareness, search friction, or skepticism of app offers & policies.",
    "habitual_expiry_quality_hesitant": "Habitual Shoppers (Expiry & Quality Hesitant): Buys routine staples but fears expired items, spoiled groceries, or stale stock in trial categories.",
    "habitual_price_sensitive": "Habitual Shoppers (Price Sensitive): Uses Myntra for daily staples but switches to Amazon/BigBasket for other categories due to prices/fees.",
    "habitual_sos_single": "Habitual Shoppers (SOS Gap-Fillers): Uses Myntra purely for urgent medicine or missing cooking ingredients and exits immediately.",
    "habitual_unaware_explorer": "Habitual Shoppers (Unaware/Browsing Friction): Unaware Myntra carries other categories or faces search/browsing friction.",
    "household_replenisher": "Shopping for family/households, buying daily groceries, staples, milk, cooking oil & vegetables.",
    "impulse_snaker_night_owl": "Ordering late-night snacks, munchies, beverages, bachelors/students looking for convenience.",
    "hesitant_multi_platformer": "Compares prices across Blinkit, Instamart, BigBasket, Amazon; sensitive to delivery charges and trust.",
    "emergency_sos_shopper": "Urgent medicine, pharmacy, guest arrivals, last-minute cooking ingredient shortages.",
    "premium_gourmet_shopper": "Buying high-value items like electronics, branded apparel, smartwatches, luxury, or gourmet imported goods.",
    "general_shopper": "General shoppers submitting positive, neutral, or general app and delivery feedback.",
    "general_shopper_positive": "General customers submitting positive feedback (4-5 stars) without specific segment keywords.",
    "general_shopper_neutral": "General customers submitting neutral/mixed feedback (3 stars).",
    "general_shopper_negative": "General customers submitting negative feedback (1-2 stars) on app errors or delivery issues.",
}


def run_segmentation_pipeline(
    reviews_file: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    in_path = reviews_file or (PROCESSED_DIR / "normalized_reviews.json")
    out_dir = output_dir or PROCESSED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading reviews from %s...", in_path)
    raw_reviews = json.loads(in_path.read_text(encoding="utf-8"))
    reviews = [NormalizedReview.from_dict(r) for r in raw_reviews]
    logger.info("Loaded %d reviews for segmentation analysis.", len(reviews))

    # Segment all reviews using stage_d_segments (LLM or heuristic)
    segment_tags = stage_d_segments(reviews)

    # Overlay habitual buyer segmented data if present
    hab_file = PROCESSED_DIR / "habitual_segmented.json"
    if hab_file.exists():
        hab_data = json.loads(hab_file.read_text(encoding="utf-8"))
        hab_map = {item["review_id"]: item["inferred_segment"] for item in hab_data}
        for tag in segment_tags:
            rid = tag.get("review_id")
            if rid in hab_map:
                tag["inferred_segment"] = hab_map[rid]

    # Compute summary counts & distributions
    segment_counts: dict[str, int] = {}
    for tag in segment_tags:
        seg = tag.get("inferred_segment", "unknown")
        segment_counts[seg] = segment_counts.get(seg, 0) + 1

    total = len(reviews) or 1
    segment_summary = [
        {
            "segment_id": seg_id,
            "label": seg_id.replace("_", " ").title(),
            "count": count,
            "percentage": round(100 * count / total, 2),
            "description": SEGMENT_DESCRIPTIONS.get(seg_id, "Customer segment"),
        }
        for seg_id, count in sorted(segment_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    output_payload = {
        "total_reviews": len(reviews),
        "summary": segment_summary,
        "segmentations": segment_tags,
    }

    # Save artifact to discovery_segments.json and segments.json
    out_file1 = out_dir / "discovery_segments.json"
    out_file2 = out_dir / "segments.json"

    out_file1.write_text(json.dumps(output_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    out_file2.write_text(json.dumps(segment_tags, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("Segmentation completed successfully!")
    logger.info("Saved output to %s and %s", out_file1, out_file2)
    return output_payload


if __name__ == "__main__":
    run_segmentation_pipeline()
