"""Taxonomy-driven scored sampling — picks which reviews are worth an
expensive LLM call for one opportunity area. Generalizes the old hardcoded
per-pipeline scorers (discovery/user-needs/multi-category subset functions)
into one function driven by src.analysis.taxonomy, since we now have 14 areas
instead of 3 fixed pipelines.
"""

from __future__ import annotations

from src.ingestion.schema import NormalizedReview
from src.analysis.taxonomy import TAXONOMY


def _word_count(text: str) -> int:
    return len(text.split())


def opportunity_subset(
    reviews: list[NormalizedReview],
    area_id: str,
    cap: int,
    already_tagged_ids: set[str] | None = None,
) -> list[NormalizedReview]:
    """Score reviews for one opportunity area and return the top `cap`.

    Score = keyword density + length quality + rating friction + thumbs_up
    + a novelty bonus for reviews not yet LLM-tagged in a prior run. The
    novelty bonus is what makes repeated runs progressively cover more of the
    corpus with LLM-quality tags instead of re-spending tokens on the same
    reviews every time (paired with the content-hash/prompt-version cache in
    src/analysis/tag_cache.py).
    """
    area = TAXONOMY[area_id]
    already_tagged_ids = already_tagged_ids or set()
    keywords = area.keywords

    scored: list[tuple[float, NormalizedReview]] = []
    for r in reviews:
        body_lower = r.body.lower()
        match_count = sum(1 for kw in keywords if kw in body_lower)
        if match_count == 0:
            continue

        words = _word_count(r.body)
        length_score = 3.0 if 15 <= words <= 120 else (1.5 if 8 <= words < 15 else 0.5)
        friction_bonus = 2.5 if r.rating <= 2 else (1.5 if r.rating == 3 else 0.5)
        thumbs_bonus = min(r.thumbs_up or 0, 5) * 0.4
        novelty_bonus = 2.0 if r.review_id not in already_tagged_ids else 0.0

        total_score = (match_count * 3.0) + length_score + friction_bonus + thumbs_bonus + novelty_bonus
        scored.append((total_score, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:cap]]
