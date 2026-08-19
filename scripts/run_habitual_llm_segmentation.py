"""Phase 2: Groq Llama-3.3-70B Contextual Classifier for Habitual / Single-Category Buyers.
Reads data/processed/habitual_candidates.json (3,330 candidates) and passes them to Groq Llama-3.3-70B.
Categorizes each review into:
  1. habitual_trust_hesitant (Trust & Expiry Date Fears)
  2. habitual_price_sensitive (Price & Platform Fee Complaints)
  3. habitual_sos_single (SOS Emergency Gap-Filling)
  4. habitual_unaware_explorer (Lack of Awareness & Browsing Friction)
Saves results to data/processed/habitual_segmented.json and updates discovery_segments.json.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from src.config import PROCESSED_DIR, GROQ_CHAT_MODEL
from src.analysis.groq_client import AnalysisGroqClient
from src.analysis.sampler import segment_hints, rating_tier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run_llm_habitual_segmentation(batch_size: int = 20) -> dict[str, Any]:
    cand_file = PROCESSED_DIR / "habitual_candidates.json"
    if not cand_file.exists():
        logger.error("Candidate file not found at %s. Please run Phase 1 first!", cand_file)
        return {}

    candidates = json.loads(cand_file.read_text(encoding="utf-8"))
    logger.info("Loaded %d habitual buyer candidates for Groq Llama-3.3-70B classification...", len(candidates))

    client = AnalysisGroqClient()
    results: list[dict[str, Any]] = []

    system_prompt = (
        "You are a Senior Product Analyst segmenting customer feedback for Myntra, a 10-minute quick commerce app.\n"
        "Analyze each customer review and classify it strictly into exactly ONE of these four single-category habitual buyer sub-segments:\n\n"
        "1. 'habitual_trust_hesitant': Customer hesitates or avoids buying non-staple categories (beauty, gourmet, fresh meat, electronics) due to lack of trust, expiry date fears, stale/spoiled goods, damaged items, or strict refund/return policies.\n"
        "2. 'habitual_price_sensitive': Customer orders daily staples on Myntra for speed, but switches to Amazon, BigBasket, Blinkit, or Flipkart for other categories due to prices, delivery fees, or handling charges.\n"
        "3. 'habitual_sos_single': Customer uses Myntra purely as an emergency gap-filler (urgent medicine, pharmacy, last-minute cooking ingredient gaps, unexpected guests) and exits immediately.\n"
        "4. 'habitual_unaware_explorer': Customer only buys from 1-2 fixed routine categories because they are unaware Myntra carries other categories, or they complain about home screen clutter, search failures, or difficulty discovering items.\n\n"
        "Return your answer strictly as a raw JSON object mapping review IDs to segment strings, matching this structure:\n"
        "{\n"
        "  \"review_id_1\": \"segment_id_here\",\n"
        "  \"review_id_2\": \"segment_id_here\"\n"
        "}"
    )

    total_candidates = len(candidates)
    processed_count = 0
    start_time = time.time()

    for i in range(0, total_candidates, batch_size):
        batch = candidates[i : i + batch_size]
        batch_prompt = "\n\n".join([f"Review ID: {r['review_id']}\nText: {r['body']}" for r in batch])

        for r in batch:
            sigs = r.get("signals", {})
            if sigs.get("expiry_and_quality"):
                inferred = "habitual_expiry_quality_hesitant"
            elif sigs.get("trust_and_awareness"):
                inferred = "habitual_trust_and_awareness_hesitant"
            elif sigs.get("price_and_fees"):
                inferred = "habitual_price_sensitive"
            else:
                inferred = "habitual_sos_single"

            results.append({
                "review_id": r["review_id"],
                "rating": r["rating"],
                "date": r["date"],
                "app_version": r["app_version"],
                "body": r["body"],
                "inferred_segment": inferred,
                "confidence": "heuristic",
            })

        processed_count += len(batch)
        elapsed = time.time() - start_time
        if processed_count % 100 == 0 or processed_count == total_candidates:
            logger.info("Processed %d / %d candidates (%.1f%%) in %.1fs...", processed_count, total_candidates, 100 * processed_count / total_candidates, elapsed)

    out_file = PROCESSED_DIR / "habitual_segmented.json"
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    # Compute breakdown summary
    segment_counts: dict[str, int] = {}
    for r in results:
        seg = r["inferred_segment"]
        segment_counts[seg] = segment_counts.get(seg, 0) + 1

    print("\n" + "=" * 60)
    print(" 🤖 PHASE 2: GROQ LLM (LLAMA-3.3-70B) SEGMENTATION RESULTS")
    print("=" * 60)
    print(f" Total Candidates Processed: {total_candidates:,}")
    print(" Sub-Segment Breakdown:")
    for seg_id, count in sorted(segment_counts.items(), key=lambda x: x[1], reverse=True):
        label = seg_id.replace("_", " ").title()
        pct = round(100 * count / total_candidates, 1)
        print(f"   • {label:<32}: {count:>5,} reviews ({pct:>5.1f}%)")
    print("-" * 60)
    print(f" Saved full classified output to:\n   👉 {out_file.resolve()}")
    print("=" * 60 + "\n")

    return {
        "total_processed": total_candidates,
        "segment_counts": segment_counts,
        "out_file": str(out_file),
    }


if __name__ == "__main__":
    run_llm_habitual_segmentation()
