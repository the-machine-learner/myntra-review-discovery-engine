"""Wishlist-usage-mode segmentation (Plan 3 Track B, screen 3): classify
wishlist-mentioning reviews into one of 5 MECE behavioral segments via a
single batched LLM pass. Reuses the batching/budget/cache infra from
llm_synthesis.py — segmentation is stored under the pseudo area_id
"_wishlist_segment" in the SAME llm_tag_cache.json used by opportunity
tagging, since tag_cache.py's functions are generic per area_id and a
second cache file would just duplicate the content-hash/prompt-version
staleness logic for no reason.

Unlike opportunity-area tagging (independent relevant/not-relevant calls per
area), segmentation is single-label: each review gets exactly one segment
(or "unclear"), so there's no "reach" concept — every candidate review is
assigned somewhere.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import PROCESSED_DIR, ANALYSIS_BATCH_SIZE, ANALYSIS_PROMPT_VERSION
from src.ingestion.schema import NormalizedReview
from src.analysis.taxonomy import classify_rule_based
from src.analysis.groq_client import AnalysisGroqClient, BudgetExhaustedError
from src.analysis import tag_cache

logger = logging.getLogger(__name__)

SEGMENTS_PATH = PROCESSED_DIR / "wishlist_segments.json"
SEGMENT_AREA_ID = "_wishlist_segment"

SEGMENT_DEFS: dict[str, dict[str, str]] = {
    "genuine_purchase_intent": {
        "label": "Genuine Purchase Intent",
        "description": "Wishlisted an item and did, or clearly intends to, actually buy it soon — an active shortlist, not a passive save.",
    },
    "price_watch": {
        "label": "Price-Drop Watch",
        "description": "Wishlisted specifically to monitor for a price drop or sale before buying.",
    },
    "bookmark_no_intent": {
        "label": "Bookmark, Not Intent",
        "description": "Treats the wishlist as a passive save/junk-drawer — items saved and forgotten, no active plan to purchase.",
    },
    "gift": {
        "label": "Gift List",
        "description": "Item saved for a future gifting occasion, not near-term self-purchase.",
    },
    "inspiration_board": {
        "label": "Inspiration Board",
        "description": "Wishlist used as a mood/style reference, not necessarily to buy the exact saved item.",
    },
    "unclear": {
        "label": "Unclear / Insufficient Signal",
        "description": "Mentions wishlist-adjacent behavior but the review doesn't give enough to confidently place it in one of the above.",
    },
}

_WISHLIST_MENTION = re.compile(r"\bwishlist\b", re.IGNORECASE)
_MOTIVATION_AREAS = {
    "wishlist_price_watch",
    "wishlist_bookmark_no_intent",
    "wishlist_gift_list",
    "wishlist_inspiration_board",
}

_SEGMENT_SYSTEM_PROMPT = """You are a product research analyst classifying customer reviews by WHY the user is using Myntra's wishlist feature.

Assign EACH review (keyed by review_id) to exactly ONE segment:
- genuine_purchase_intent: {genuine_purchase_intent}
- price_watch: {price_watch}
- bookmark_no_intent: {bookmark_no_intent}
- gift: {gift}
- inspiration_board: {inspiration_board}
- unclear: {unclear}

Return ONLY a JSON object: {{"review_id_1": {{"segment": "price_watch"}}, ...}}
If a review doesn't actually discuss wishlist usage at all (false keyword match), still assign "unclear".
"""


def candidate_pool(reviews: list[NormalizedReview]) -> list[NormalizedReview]:
    """Reviews worth segmenting: anything that literally says "wishlist", plus
    anything the taxonomy's 4 wishlist-motivation areas already rule-tagged
    (covers phrasing that discusses the behavior without the literal word)."""
    out = []
    for r in reviews:
        if not r.body:
            continue
        if _WISHLIST_MENTION.search(r.body) or (_MOTIVATION_AREAS & set(classify_rule_based(r.body))):
            out.append(r)
    return out


def estimate_segment_cost(reviews: list[NormalizedReview]) -> dict[str, Any]:
    cache = tag_cache.load_cache()
    pool = candidate_pool(reviews)
    to_tag = [r for r in pool if tag_cache.needs_llm_tagging(r, SEGMENT_AREA_ID, cache)]
    batch_calls = -(-len(to_tag) // ANALYSIS_BATCH_SIZE) if to_tag else 0
    tokens_est = len(to_tag) * 150 + batch_calls * 400
    return {
        "candidate_pool_size": len(pool),
        "reviews_needing_llm_tag": len(to_tag),
        "estimated_calls": batch_calls,
        "estimated_tokens": tokens_est,
    }


def run_segmentation(reviews: list[NormalizedReview]) -> dict[str, Any]:
    cache = tag_cache.load_cache()
    client = AnalysisGroqClient()
    pool = candidate_pool(reviews)
    pool_by_id = {r.review_id: r for r in pool}

    to_tag: list[NormalizedReview] = []
    for review in pool:
        if tag_cache.needs_llm_tagging(review, SEGMENT_AREA_ID, cache):
            to_tag.append(review)

    logger.info("Wishlist segmentation: %d candidates, %d need LLM tagging", len(pool), len(to_tag))

    system_prompt = _SEGMENT_SYSTEM_PROMPT.format(
        **{k: v["description"] for k, v in SEGMENT_DEFS.items()}
    )

    for batch_start in range(0, len(to_tag), ANALYSIS_BATCH_SIZE):
        batch = to_tag[batch_start: batch_start + ANALYSIS_BATCH_SIZE]
        if not batch:
            continue
        user_prompt = "\n\n".join(
            f"review_id: {r.review_id}\nbody: {r.body}" for r in batch
        )
        try:
            result = client.chat_json(system_prompt, user_prompt)
        except BudgetExhaustedError:
            logger.warning("Groq budget exhausted mid-segmentation; stopping")
            break
        except Exception as exc:
            logger.warning("LLM segmentation batch failed: %s", exc)
            continue

        if not isinstance(result, dict):
            continue
        for review in batch:
            tag_result = result.get(review.review_id)
            if not isinstance(tag_result, dict) or tag_result.get("segment") not in SEGMENT_DEFS:
                continue
            tag_cache.record_llm_tag(
                review, SEGMENT_AREA_ID, tag_result, rule_tags=["_wishlist_segment"], cache=cache
            )

    tag_cache.save_cache(cache)

    # Build final counts/quotes from the FULL accumulated cache for this
    # pseudo-area (same reasoning as llm_synthesis.py's sample-drift fix —
    # never just this run's batch).
    assignments: dict[str, str] = {}
    for rid, review in pool_by_id.items():
        cached = tag_cache.get_cached_llm_tag(rid, SEGMENT_AREA_ID, cache)
        if cached and cached.get("segment") in SEGMENT_DEFS:
            assignments[rid] = cached["segment"]

    segment_counts: dict[str, list[str]] = {seg_id: [] for seg_id in SEGMENT_DEFS}
    for rid, seg_id in assignments.items():
        segment_counts[seg_id].append(rid)

    total_classified = len(assignments)
    segments_out = []
    for seg_id, seg_def in SEGMENT_DEFS.items():
        rids = segment_counts[seg_id]
        quotes = []
        for rid in rids[:3]:
            review = pool_by_id[rid]
            quotes.append(
                {
                    "review_id": rid,
                    "text": review.body[:280],
                    "rating": review.rating,
                    "platform": review.platform,
                    "date": review.date,
                }
            )
        segments_out.append(
            {
                "segment_id": seg_id,
                "label": seg_def["label"],
                "description": seg_def["description"],
                "count": len(rids),
                "pct_of_classified": round(100 * len(rids) / total_classified, 1) if total_classified else 0.0,
                "quotes": quotes,
            }
        )
    segments_out.sort(key=lambda s: s["count"], reverse=True)

    run_metadata = {
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "prompt_version": ANALYSIS_PROMPT_VERSION,
        "candidate_pool_size": len(pool),
        "total_classified": total_classified,
        "groq_call_count": client.call_count,
        "estimated_tokens_used": client.estimated_tokens,
    }

    output = {"run_metadata": run_metadata, "segments": segments_out}
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    SEGMENTS_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    return output
