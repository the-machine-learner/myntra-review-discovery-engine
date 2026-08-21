"""Batched per-area LLM synthesis: relevance confirmation, severity scoring,
and PM-readable summary generation. Never 1-call-per-review — reviews are
batched into ANALYSIS_BATCH_SIZE-sized chunks per call, then one merge call
per area produces the final ~150-word synthesis. Reviews already cached for
this area + the current ANALYSIS_PROMPT_VERSION are reused, never re-tagged.
"""

from __future__ import annotations

import logging
from typing import Any

from src.config import ANALYSIS_BATCH_SIZE, ANALYSIS_PROMPT_VERSION
from src.ingestion.schema import NormalizedReview
from src.analysis.taxonomy import OpportunityArea
from src.analysis.groq_client import AnalysisGroqClient, BudgetExhaustedError
from src.analysis import tag_cache

logger = logging.getLogger(__name__)

_BATCH_SYSTEM_PROMPT = """You are a product research analyst tagging customer reviews for one specific opportunity area in a wishlist-to-purchase-conversion study.

Opportunity area: {label}
Definition: {description}

For EACH review given (keyed by review_id), decide:
- "relevant": true only if the review genuinely discusses this specific opportunity area (not just a coincidental keyword match)
- "severity": integer 1-5, how strongly this review expresses friction/pain from this issue (1=mild mention, 5=severe/blocking)
- "quote": a SHORT (<=200 characters) VERBATIM excerpt copied exactly from the review body that best illustrates the issue, or null if not relevant

Return ONLY a JSON object: {{"review_id_1": {{"relevant": true, "severity": 3, "quote": "..."}}, ...}}
Never invent or paraphrase quotes — copy exact substrings only. Never include PII (emails, phone numbers).
"""

_MERGE_SYSTEM_PROMPT = """You are a Senior Product Manager writing an executive synthesis of one opportunity area for a wishlist-to-purchase-conversion study.

Opportunity area: {label}
Definition: {description}

You are given confirmed-relevant customer review excerpts with severity scores. Write a synthesis of AT MOST 150 words that:
1. Describes the pattern/theme in this feedback
2. Notes what this suggests about why wishlisted items don't convert to purchases
3. Is concrete and PM-readable, not generic

Return ONLY a JSON object: {{"synthesis": "..."}}
Never invent facts not supported by the given excerpts. Never include PII.
"""


def synthesize_area(
    client: AnalysisGroqClient,
    area: OpportunityArea,
    sample: list[NormalizedReview],
    batch_size: int = ANALYSIS_BATCH_SIZE,
    cache: dict[str, dict[str, Any]] | None = None,
    reviews_by_id: dict[str, NormalizedReview] | None = None,
) -> dict[str, Any]:
    """Run the two-stage LLM synthesis (batched relevance/severity/quote
    tagging, then one merge call) for one opportunity area.

    `sample` is only what THIS run tags (fresh, budget-bounded). The final
    synthesis/quotes are built from the FULL accumulated cache for this area
    across ALL runs (filtered to the current ANALYSIS_PROMPT_VERSION) — not
    just this run's sample. This matters because the sampler's novelty bonus
    deliberately shifts which reviews get sampled run to run to expand
    coverage over time; without this, a genuinely-confirmed finding from an
    earlier run would silently vanish the moment a later run's sample
    composition drifted away from it. `reviews_by_id` should cover the full
    corpus (not just `sample`) so a cache hit from a past run's sample can
    still be resolved to its review object for quote/date/platform display.

    Returns a dict with llm_synthesis, top_quotes, llm_avg_severity,
    llm_sample_n, llm_relevant_n.
    """
    cache = cache if cache is not None else tag_cache.load_cache()

    to_tag: list[NormalizedReview] = []
    reused: dict[str, dict[str, Any]] = {}
    for review in sample:
        if tag_cache.needs_llm_tagging(review, area.area_id, cache):
            to_tag.append(review)
        else:
            cached = tag_cache.get_cached_llm_tag(review.review_id, area.area_id, cache)
            if cached is not None:
                reused[review.review_id] = cached

    tagged: dict[str, dict[str, Any]] = dict(reused)
    logger.info(
        "Area %s: %d reused from cache, %d need LLM tagging",
        area.area_id, len(reused), len(to_tag),
    )

    for batch_start in range(0, len(to_tag), batch_size):
        batch = to_tag[batch_start : batch_start + batch_size]
        if not batch:
            continue
        user_prompt = "\n\n".join(
            f"review_id: {r.review_id}\nrating: {r.rating}\nbody: {r.body}" for r in batch
        )
        system_prompt = _BATCH_SYSTEM_PROMPT.format(label=area.label, description=area.description)
        try:
            result = client.chat_json(system_prompt, user_prompt)
        except BudgetExhaustedError:
            logger.warning(
                "Groq budget exhausted mid-synthesis for area %s; stopping batch tagging", area.area_id
            )
            break
        except Exception as exc:
            logger.warning("LLM batch tagging failed for area %s: %s", area.area_id, exc)
            continue

        if not isinstance(result, dict):
            continue
        for review in batch:
            tag_result = result.get(review.review_id)
            if not isinstance(tag_result, dict):
                continue
            # Enforce "verbatim substring only" at the source, not just at
            # final validation. A real run produced a quote that spliced two
            # non-adjacent sentences from one review together — each half was
            # real text, but concatenated it wasn't an actual substring, so
            # validate_opportunity_synthesis correctly flagged it downstream.
            # Null the quote here instead (keep relevant/severity, which are
            # independently plausible) so a spliced/paraphrased quote never
            # gets cached or shown as if it were a real customer excerpt.
            quote = tag_result.get("quote")
            if quote and quote not in review.body:
                tag_result = {**tag_result, "quote": None}
            tagged[review.review_id] = tag_result
            tag_cache.record_llm_tag(
                review, area.area_id, tag_result, rule_tags=[area.area_id], cache=cache
            )

    tag_cache.save_cache(cache)

    reviews_by_id = reviews_by_id if reviews_by_id is not None else {r.review_id: r for r in sample}

    # Build from the FULL cache for this area + current prompt version, not
    # just this run's `tagged` dict — see docstring for why.
    all_area_entries = [
        (rid, entry["llm_tags"][area.area_id])
        for rid, entry in cache.items()
        if area.area_id in entry.get("llm_tags", {})
        and entry.get("prompt_version") == ANALYSIS_PROMPT_VERSION
        and rid in reviews_by_id
    ]
    relevant_entries = [(rid, t) for rid, t in all_area_entries if t.get("relevant")]

    if not relevant_entries:
        return {
            "llm_synthesis": "",
            "top_quotes": [],
            "llm_avg_severity": 0.0,
            "llm_sample_n": len(all_area_entries),
            "llm_relevant_n": 0,
        }

    severities = [float(t.get("severity") or 0) for _, t in relevant_entries]
    avg_severity = sum(severities) / len(severities) if severities else 0.0

    quotes_ranked = sorted(relevant_entries, key=lambda x: x[1].get("severity") or 0, reverse=True)
    top_quotes = []
    for rid, t in quotes_ranked[:5]:
        quote_text = t.get("quote")
        if not quote_text:
            continue
        review = reviews_by_id[rid]
        top_quotes.append(
            {
                "review_id": rid,
                "text": quote_text,
                "rating": review.rating,
                "platform": review.platform,
                "date": review.date,
            }
        )

    merge_user_prompt = "\n\n".join(
        f"review_id: {rid} | severity: {t.get('severity')} | quote: {t.get('quote')}"
        for rid, t in quotes_ranked[:20]
    )
    merge_system_prompt = _MERGE_SYSTEM_PROMPT.format(label=area.label, description=area.description)

    synthesis_text = ""
    try:
        merge_result = client.chat_json(merge_system_prompt, merge_user_prompt)
        if isinstance(merge_result, dict):
            synthesis_text = str(merge_result.get("synthesis") or "")
    except BudgetExhaustedError:
        logger.warning("Groq budget exhausted before merge call for area %s", area.area_id)
    except Exception as exc:
        logger.warning("LLM merge synthesis failed for area %s: %s", area.area_id, exc)

    return {
        "llm_synthesis": synthesis_text,
        "top_quotes": top_quotes[:3],
        "llm_avg_severity": round(avg_severity, 2),
        "llm_sample_n": len(all_area_entries),
        "llm_relevant_n": len(relevant_entries),
    }
