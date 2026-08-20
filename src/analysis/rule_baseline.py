"""Zero-cost, rule-based full-corpus tagging and reach statistics. Runs on
100% of the corpus regardless of which areas are in-scope for LLM synthesis
this run — this alone answers "how much signal exists" before spending a
single Groq token.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from src.ingestion.schema import NormalizedReview
from src.analysis.taxonomy import TAXONOMY, classify_rule_based


def tag_corpus_rule_based(reviews: list[NormalizedReview]) -> dict[str, list[str]]:
    """review_id -> matched area_ids, for every review in the corpus."""
    return {review.review_id: classify_rule_based(review.body) for review in reviews}


@dataclass
class ReachStats:
    area_id: str
    matched_count: int
    corpus_size: int
    pct: float
    avg_rating_of_matches: float
    platform_breakdown: dict[str, int] = field(default_factory=dict)


def compute_reach_stats(
    reviews: list[NormalizedReview],
    tags: dict[str, list[str]],
) -> dict[str, ReachStats]:
    corpus_size = len(reviews)
    reviews_by_id = {r.review_id: r for r in reviews}

    matches_by_area: dict[str, list[str]] = {area_id: [] for area_id in TAXONOMY}
    for review_id, area_ids in tags.items():
        for area_id in area_ids:
            if area_id in matches_by_area:
                matches_by_area[area_id].append(review_id)

    stats: dict[str, ReachStats] = {}
    for area_id, matched_ids in matches_by_area.items():
        matched_reviews = [reviews_by_id[rid] for rid in matched_ids if rid in reviews_by_id]
        matched_count = len(matched_reviews)
        avg_rating = (
            sum(r.rating for r in matched_reviews) / matched_count if matched_count else 0.0
        )
        platform_breakdown = dict(Counter(r.platform for r in matched_reviews))
        stats[area_id] = ReachStats(
            area_id=area_id,
            matched_count=matched_count,
            corpus_size=corpus_size,
            pct=round((matched_count / corpus_size * 100) if corpus_size else 0.0, 2),
            avg_rating_of_matches=round(avg_rating, 2),
            platform_breakdown=platform_breakdown,
        )
    return stats
