"""Reach / Impact / Confidence scoring — combines the free rule-based reach
stats (full corpus) with the expensive LLM synthesis results (sampled subset)
into one comparable score per opportunity area. Every derived number ships
alongside its raw inputs in the output artifact — never a black-box score.

Deliberately does NOT fabricate an "Effort" number — no regex or LLM can
honestly estimate engineering effort. See data/processed/
opportunity_effort_overrides.json (PM-editable, this module never writes to
it) for where that judgment call lives instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.analysis.rule_baseline import ReachStats
from src.analysis.taxonomy import OpportunityArea


@dataclass
class OpportunityScore:
    area_id: str
    label: str
    feasible_without_monetary_incentive: str
    reach: dict[str, Any]
    impact: dict[str, Any]
    confidence: dict[str, Any]
    signal_score: float
    trend: dict[str, Any]
    top_quotes: list[dict[str, Any]] = field(default_factory=list)
    llm_synthesis: str = ""
    supporting_review_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "area_id": self.area_id,
            "label": self.label,
            "feasible_without_monetary_incentive": self.feasible_without_monetary_incentive,
            "reach": self.reach,
            "impact": self.impact,
            "confidence": self.confidence,
            "signal_score": self.signal_score,
            "trend": self.trend,
            "top_quotes": self.top_quotes,
            "llm_synthesis": self.llm_synthesis,
            "supporting_review_ids": self.supporting_review_ids,
        }


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def score_opportunities(
    reach_stats: dict[str, ReachStats],
    llm_results: dict[str, dict[str, Any]],
    taxonomy: dict[str, OpportunityArea],
    prior_scores: dict[str, dict[str, Any]] | None = None,
) -> list[OpportunityScore]:
    """Score every area present in `llm_results` (i.e. areas that were
    actually run through LLM synthesis this run — see --areas CLI filter).
    `reach_stats` should cover the full corpus regardless of scope (it's
    free); `prior_scores` is the previous opportunity_scores.json content
    (area_id -> dict), if any, for trend deltas.
    """
    prior_scores = prior_scores or {}
    area_ids = list(llm_results.keys())

    max_reach_pct = max((reach_stats[aid].pct for aid in area_ids if aid in reach_stats), default=0.0)

    scores: list[OpportunityScore] = []
    for area_id in area_ids:
        area = taxonomy.get(area_id)
        if area is None:
            continue
        reach = reach_stats.get(area_id)
        llm = llm_results.get(area_id, {})

        matched_count = reach.matched_count if reach else 0
        corpus_size = reach.corpus_size if reach else 0
        reach_pct = reach.pct if reach else 0.0
        avg_rating = reach.avg_rating_of_matches if reach else 0.0
        platform_breakdown = reach.platform_breakdown if reach else {}

        llm_avg_severity = float(llm.get("llm_avg_severity", 0.0))
        llm_sample_n = int(llm.get("llm_sample_n", 0))
        llm_relevant_n = int(llm.get("llm_relevant_n", 0))

        # Impact: blend the free rating-based proxy with the (if available)
        # LLM-assessed severity, which is a more direct read on how strongly
        # a review expresses friction from this specific issue.
        rating_impact_score = _clamp(((5.0 - avg_rating) / 4.0) * 100.0) if matched_count else 0.0
        llm_severity_score = _clamp((llm_avg_severity / 5.0) * 100.0) if llm_avg_severity else 0.0
        if llm_sample_n > 0:
            blended_impact_score = round(rating_impact_score * 0.4 + llm_severity_score * 0.6, 1)
        else:
            blended_impact_score = round(rating_impact_score, 1)

        # Confidence: how much of the matched population did the LLM
        # actually review (coverage), and how often did it confirm the cheap
        # regex match was truly relevant (agreement/precision)?
        sample_coverage_pct = round((llm_sample_n / matched_count * 100.0), 2) if matched_count else 0.0
        rule_llm_agreement_pct = (
            round((llm_relevant_n / llm_sample_n * 100.0), 1) if llm_sample_n else 0.0
        )
        cross_platform_count = len(platform_breakdown)
        confidence_score = round(
            _clamp(sample_coverage_pct * 5.0) * 0.4 + rule_llm_agreement_pct * 0.6, 1
        )

        # Reach normalized relative to the other areas scored this run (a
        # raw 5% hit rate is "high" if nothing else clears 2%, "low" if
        # everything else clears 20% — relative framing is more honest than
        # an arbitrary fixed scale).
        reach_score_norm = round((reach_pct / max_reach_pct * 100.0), 1) if max_reach_pct else 0.0

        signal_score = round(
            reach_score_norm * 0.4 + blended_impact_score * 0.35 + confidence_score * 0.25, 1
        )

        prior = prior_scores.get(area_id, {})
        prior_pct = prior.get("reach", {}).get("pct")
        trend = {
            "prior_run_pct": prior_pct,
            "delta_pp": round(reach_pct - prior_pct, 2) if prior_pct is not None else None,
        }

        scores.append(
            OpportunityScore(
                area_id=area_id,
                label=area.label,
                feasible_without_monetary_incentive=area.feasible_without_monetary_incentive,
                reach={
                    "matched_count": matched_count,
                    "corpus_size": corpus_size,
                    "pct": reach_pct,
                    "platform_breakdown": platform_breakdown,
                },
                impact={
                    "avg_rating_of_matches": avg_rating,
                    "rating_impact_score": round(rating_impact_score, 1),
                    "llm_avg_severity": llm_avg_severity,
                    "llm_severity_score": round(llm_severity_score, 1),
                    "blended_impact_score": blended_impact_score,
                    "llm_sample_n": llm_sample_n,
                },
                confidence={
                    "sample_coverage_pct": sample_coverage_pct,
                    "cross_platform_count": cross_platform_count,
                    "rule_llm_agreement_pct": rule_llm_agreement_pct,
                    "confidence_score": confidence_score,
                },
                signal_score=signal_score,
                trend=trend,
                top_quotes=llm.get("top_quotes", []),
                llm_synthesis=llm.get("llm_synthesis", ""),
                supporting_review_ids=[q["review_id"] for q in llm.get("top_quotes", [])],
            )
        )

    scores.sort(key=lambda s: s.signal_score, reverse=True)
    return scores
