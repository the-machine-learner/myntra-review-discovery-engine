"""Orchestrates the analysis pipeline: rule-tag (full corpus, $0) -> sample
(per area) -> LLM-synthesize (batched, budget-gated) -> score -> write
artifacts. This is what src/analysis/run.py's CLI drives.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import (
    PROCESSED_DIR,
    OPPORTUNITY_SAMPLE_CAP_PER_AREA,
    ANALYSIS_PROMPT_VERSION,
    ANALYSIS_BATCH_SIZE,
    GROQ_CHAT_MODEL,
)
from src.ingestion.schema import NormalizedReview
from src.analysis.taxonomy import TAXONOMY, MVP_AREA_IDS
from src.analysis.rule_baseline import tag_corpus_rule_based, compute_reach_stats
from src.analysis.sampler import opportunity_subset
from src.analysis.llm_synthesis import synthesize_area
from src.analysis.scoring import score_opportunities, OpportunityScore
from src.analysis.groq_client import AnalysisGroqClient, BudgetExhaustedError
from src.analysis.validators import validate_opportunity_synthesis
from src.analysis import tag_cache

logger = logging.getLogger(__name__)

OPPORTUNITY_SCORES_PATH = PROCESSED_DIR / "opportunity_scores.json"
RUN_METADATA_PATH = PROCESSED_DIR / "opportunity_run_metadata.json"


def load_reviews(path: Path) -> list[NormalizedReview]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [NormalizedReview.from_dict(item) for item in raw]


def _load_prior_scores() -> dict[str, dict[str, Any]]:
    if not OPPORTUNITY_SCORES_PATH.exists():
        return {}
    try:
        prior_list = json.loads(OPPORTUNITY_SCORES_PATH.read_text(encoding="utf-8"))
        return {s["area_id"]: s for s in prior_list}
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return {}


def estimate_run_cost(
    reviews: list[NormalizedReview],
    area_ids: list[str],
    sample_cap: int | None = None,
) -> dict[str, Any]:
    """Estimate calls/tokens for a run against `area_ids` BEFORE spending
    anything — used by `--dry-run-budget`."""
    cache = tag_cache.load_cache()
    sample_cap = sample_cap or OPPORTUNITY_SAMPLE_CAP_PER_AREA

    total_calls = 0
    total_tokens_est = 0
    per_area: dict[str, Any] = {}
    for area_id in area_ids:
        already = tag_cache.already_tagged_ids(area_id, cache)
        sample = opportunity_subset(reviews, area_id, sample_cap, already_tagged_ids=already)
        to_tag = [r for r in sample if tag_cache.needs_llm_tagging(r, area_id, cache)]
        batch_calls = -(-len(to_tag) // ANALYSIS_BATCH_SIZE) if to_tag else 0  # ceil div
        merge_calls = 1 if sample else 0
        calls = batch_calls + merge_calls
        # Crude estimate: ~150 tokens/review body + ~400 tokens prompt overhead/call.
        tokens_est = len(to_tag) * 150 + calls * 400
        per_area[area_id] = {
            "sample_size": len(sample),
            "reviews_needing_llm_tag": len(to_tag),
            "estimated_calls": calls,
            "estimated_tokens": tokens_est,
        }
        total_calls += calls
        total_tokens_est += tokens_est

    return {
        "total_estimated_calls": total_calls,
        "total_estimated_tokens": total_tokens_est,
        "per_area": per_area,
    }


def run_analysis(
    reviews_path: Path,
    area_ids: list[str] | None = None,
    skip_llm: bool = False,
    sample_cap: int | None = None,
) -> dict[str, Any]:
    reviews = load_reviews(reviews_path)
    area_ids = area_ids or list(MVP_AREA_IDS)
    sample_cap = sample_cap or OPPORTUNITY_SAMPLE_CAP_PER_AREA
    reviews_by_id = {r.review_id: r for r in reviews}

    logger.info("=== Stage: rule-based full-corpus tagging ($0) ===")
    tags = tag_corpus_rule_based(reviews)
    reach_stats = compute_reach_stats(reviews, tags)
    prior_scores = _load_prior_scores()

    run_metadata: dict[str, Any] = {
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "prompt_version": ANALYSIS_PROMPT_VERSION,
        "model_id": GROQ_CHAT_MODEL,
        "corpus_size_at_run": len(reviews),
        "area_ids": area_ids,
        "groq_call_count": 0,
        "estimated_tokens_used": 0,
        "per_area_sample_sizes": {},
        "validation_ok": True,
        "validation_errors": [],
    }

    if skip_llm:
        logger.info("--skip-llm set: rule-only dry run, no Groq calls made")
        empty_llm_results: dict[str, dict[str, Any]] = {aid: {} for aid in area_ids}
        scores = score_opportunities(reach_stats, empty_llm_results, TAXONOMY, prior_scores)
        save_artifacts(scores, run_metadata)
        return {"scores": [s.to_dict() for s in scores], "run_metadata": run_metadata}

    cache = tag_cache.load_cache()
    client = AnalysisGroqClient()
    llm_results: dict[str, dict[str, Any]] = {}

    for area_id in area_ids:
        area = TAXONOMY[area_id]
        logger.info("=== Stage: sampling + LLM synthesis for %s ===", area_id)
        already = tag_cache.already_tagged_ids(area_id, cache)
        sample = opportunity_subset(reviews, area_id, sample_cap, already_tagged_ids=already)
        run_metadata["per_area_sample_sizes"][area_id] = len(sample)

        if not sample:
            logger.info("No reviews matched %s; skipping LLM synthesis", area_id)
            llm_results[area_id] = {}
            continue

        try:
            result = synthesize_area(client, area, sample, cache=cache, reviews_by_id=reviews_by_id)
        except BudgetExhaustedError:
            logger.warning("Groq budget exhausted; stopping remaining areas after %s", area_id)
            llm_results[area_id] = {}
            break

        if result.get("llm_synthesis"):
            validation = validate_opportunity_synthesis(
                area_id, result["llm_synthesis"], result.get("top_quotes", []), reviews_by_id
            )
            if not validation.ok:
                run_metadata["validation_ok"] = False
                run_metadata["validation_errors"].extend(validation.errors)
                logger.warning("Validation issues for %s: %s", area_id, validation.errors)

        llm_results[area_id] = result

    run_metadata["groq_call_count"] = client.call_count
    run_metadata["estimated_tokens_used"] = client.estimated_tokens

    scores = score_opportunities(reach_stats, llm_results, TAXONOMY, prior_scores)
    save_artifacts(scores, run_metadata)
    return {"scores": [s.to_dict() for s in scores], "run_metadata": run_metadata}


def save_artifacts(scores: list[OpportunityScore], run_metadata: dict[str, Any]) -> None:
    """Write opportunity_scores.json, MERGING with any existing areas not
    included in this run — a partial `--areas` run must only update the
    areas it actually processed, never silently drop the others. (This was a
    real bug: the first version overwrote the whole file with only the
    current run's areas, losing every other area's results.)
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    existing_by_id: dict[str, dict[str, Any]] = {}
    if OPPORTUNITY_SCORES_PATH.exists():
        try:
            existing_list = json.loads(OPPORTUNITY_SCORES_PATH.read_text(encoding="utf-8"))
            existing_by_id = {s["area_id"]: s for s in existing_list if isinstance(s, dict) and "area_id" in s}
        except (OSError, json.JSONDecodeError):
            existing_by_id = {}

    for score in scores:
        existing_by_id[score.area_id] = score.to_dict()

    merged = sorted(existing_by_id.values(), key=lambda s: s.get("signal_score", 0), reverse=True)

    OPPORTUNITY_SCORES_PATH.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    RUN_METADATA_PATH.write_text(
        json.dumps(run_metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
