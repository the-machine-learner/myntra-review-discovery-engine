"""Incremental LLM-tag cache: data/processed/llm_tag_cache.json.

Mirrors run_embed_all()'s content-hash pending-detection but adds a
prompt_version dimension (prompts iterate far more than the embedding model
does) — a review needs (re)LLM-tagging if it's not yet cached, its content
changed, the taxonomy/prompt version bumped, or it simply hasn't been tagged
for this specific area yet.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.config import PROCESSED_DIR, ANALYSIS_PROMPT_VERSION
from src.ingestion.schema import NormalizedReview
from src.embeddings.store import content_hash

CACHE_PATH = PROCESSED_DIR / "llm_tag_cache.json"


def load_cache() -> dict[str, dict[str, Any]]:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict[str, dict[str, Any]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def needs_llm_tagging(review: NormalizedReview, area_id: str, cache: dict[str, dict[str, Any]]) -> bool:
    entry = cache.get(review.review_id)
    if entry is None:
        return True
    if entry.get("content_hash") != content_hash(review.body):
        return True
    if entry.get("prompt_version") != ANALYSIS_PROMPT_VERSION:
        return True
    if area_id not in entry.get("llm_tags", {}):
        return True
    return False


def get_cached_llm_tag(review_id: str, area_id: str, cache: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    entry = cache.get(review_id)
    if not entry:
        return None
    return entry.get("llm_tags", {}).get(area_id)


def already_tagged_ids(area_id: str, cache: dict[str, dict[str, Any]]) -> set[str]:
    """review_ids that already have a cached, current-prompt-version LLM tag
    for this area — used by sampler.opportunity_subset's novelty bonus so
    repeated runs progressively cover more of the corpus."""
    return {
        rid
        for rid, entry in cache.items()
        if area_id in entry.get("llm_tags", {}) and entry.get("prompt_version") == ANALYSIS_PROMPT_VERSION
    }


def record_llm_tag(
    review: NormalizedReview,
    area_id: str,
    tag_result: dict[str, Any],
    rule_tags: list[str],
    cache: dict[str, dict[str, Any]],
) -> None:
    entry = cache.setdefault(review.review_id, {})
    entry["content_hash"] = content_hash(review.body)
    entry["rule_tags"] = rule_tags
    entry["prompt_version"] = ANALYSIS_PROMPT_VERSION
    entry["tagged_at"] = datetime.now(timezone.utc).isoformat()
    entry.setdefault("llm_tags", {})[area_id] = tag_result
