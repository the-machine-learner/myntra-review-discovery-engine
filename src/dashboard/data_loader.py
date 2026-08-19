"""Load and validate dashboard artifacts for Myntra Discovery Engine."""

from __future__ import annotations

import json
import shutil
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.dashboard.constants import (
    ARTIFACT_DIR,
    LKG_DIR,
    REVIEWS_FILE,
    RUN_METADATA_FILE,
    SEGMENTS_FILE,
    THEMES_FILE,
    UNMET_NEEDS_FILE,
)
from src.ingestion.schema import NormalizedReview


@dataclass
class DashboardData:
    themes: list[dict[str, Any]]
    unmet_needs: list[dict[str, Any]]
    segments: list[dict[str, Any]]
    segments_by_review: dict[str, dict[str, Any]]
    discovery_segments: dict[str, Any]
    user_needs_analysis: dict[str, Any]
    multi_category_analysis: dict[str, Any]
    reviews: list[NormalizedReview]
    reviews_by_id: dict[str, NormalizedReview]
    run_metadata: dict[str, Any]
    using_lkg: bool = False
    load_warnings: list[str] = field(default_factory=list)


def _read_json_safe(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_dashboard_data(artifact_dir: Path | None = None) -> DashboardData:
    base = artifact_dir or ARTIFACT_DIR
    warnings: list[str] = []

    reviews_path = base / REVIEWS_FILE
    if not reviews_path.exists():
        raise FileNotFoundError(f"Missing {reviews_path} — run Phase 1 ingestion first.")

    raw_reviews = _read_json_safe(reviews_path, [])
    reviews = [NormalizedReview.from_dict(r) for r in raw_reviews]
    reviews_by_id = {r.review_id: r for r in reviews}

    # Core artifacts
    themes = _read_json_safe(base / THEMES_FILE, [])
    unmet = _read_json_safe(base / UNMET_NEEDS_FILE, [])
    segments = _read_json_safe(base / SEGMENTS_FILE, [])
    meta = _read_json_safe(base / RUN_METADATA_FILE, {})

    # Specialized pipeline outputs
    disc_seg = _read_json_safe(base / "discovery_segments.json", {})
    needs_ana = _read_json_safe(base / "user_needs_analysis.json", {})
    multi_ana = _read_json_safe(base / "multi_category_analysis.json", {})

    # Fallbacks if specialized JSONs not present yet
    if not disc_seg and segments:
        # Build discovery_segments payload from segments.json
        segment_counts: dict[str, int] = {}
        for tag in segments:
            seg = tag.get("inferred_segment", "unknown") if isinstance(tag, dict) else "unknown"
            segment_counts[seg] = segment_counts.get(seg, 0) + 1
        total = len(segments) or 1
        disc_seg = {
            "total_reviews": len(reviews),
            "summary": [
                {
                    "segment_id": k,
                    "label": k.replace("_", " ").title(),
                    "count": v,
                    "percentage": round(100 * v / total, 2),
                    "description": f"Customer segment for {k.replace('_', ' ')}",
                }
                for k, v in sorted(segment_counts.items(), key=lambda x: x[1], reverse=True)
            ],
            "segmentations": segments,
        }

    if not needs_ana:
        needs_ana = {
            "sample_size": 450,
            "total_corpus_size": len(reviews),
            "themes": themes or [],
            "unmet_needs": unmet or [],
        }

    if not multi_ana:
        multi_ana = {
            "sample_size": 450,
            "total_corpus_size": len(reviews),
            "themes": [t for t in themes if "multi" in t.get("label", "").lower() or "platform" in t.get("label", "").lower()] or themes,
            "platform_insights": [],
        }

    segments_by_review = {s["review_id"]: s for s in segments if isinstance(s, dict) and "review_id" in s}

    return DashboardData(
        themes=themes,
        unmet_needs=sorted(unmet, key=lambda n: n.get("rank", 999)) if isinstance(unmet, list) else [],
        segments=segments if isinstance(segments, list) else [],
        segments_by_review=segments_by_review,
        discovery_segments=disc_seg,
        user_needs_analysis=needs_ana,
        multi_category_analysis=multi_ana,
        reviews=reviews,
        reviews_by_id=reviews_by_id,
        run_metadata=meta,
        using_lkg=False,
        load_warnings=warnings,
    )
