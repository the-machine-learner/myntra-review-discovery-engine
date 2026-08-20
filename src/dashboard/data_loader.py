"""Load and validate dashboard artifacts for the Myntra Wishlist Discovery
Engine. Ports the soft-load-never-raise pattern from reference/app
(`_read_json_safe` — missing/corrupt optional artifacts degrade gracefully,
only `normalized_reviews.json` is required), rebuilt around the new
opportunity-scoring artifact schema (src/analysis/pipeline.py's output)
instead of the old theme/segment/unmet-needs shape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.dashboard.constants import (
    ARTIFACT_DIR,
    REVIEWS_FILE,
    OPPORTUNITY_SCORES_FILE,
    OPPORTUNITY_RUN_METADATA_FILE,
)
from src.ingestion.schema import NormalizedReview


@dataclass
class DashboardData:
    reviews: list[NormalizedReview]
    reviews_by_id: dict[str, NormalizedReview]
    opportunities: list[dict[str, Any]]
    opportunity_run_metadata: dict[str, Any]
    load_warnings: list[str] = field(default_factory=list)


def _read_json_safe(path: Path, default: Any, warnings: list[str]) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        warnings.append(f"Failed to read {path.name}: {e}")
        return default


def load_dashboard_data(artifact_dir: Path | None = None) -> DashboardData:
    artifact_dir = artifact_dir or ARTIFACT_DIR
    warnings: list[str] = []

    reviews_path = artifact_dir / REVIEWS_FILE
    if not reviews_path.exists():
        raise FileNotFoundError(
            f"{reviews_path} not found — run ingestion first "
            "(python -m src.ops.run refresh)."
        )
    raw_reviews = json.loads(reviews_path.read_text(encoding="utf-8"))
    reviews = [NormalizedReview.from_dict(r) for r in raw_reviews]
    reviews_by_id = {r.review_id: r for r in reviews}

    opportunities = _read_json_safe(artifact_dir / OPPORTUNITY_SCORES_FILE, [], warnings)
    if not isinstance(opportunities, list):
        warnings.append(f"{OPPORTUNITY_SCORES_FILE} was not a list — ignoring")
        opportunities = []

    opportunity_run_metadata = _read_json_safe(artifact_dir / OPPORTUNITY_RUN_METADATA_FILE, {}, warnings)
    if not isinstance(opportunity_run_metadata, dict):
        opportunity_run_metadata = {}

    return DashboardData(
        reviews=reviews,
        reviews_by_id=reviews_by_id,
        opportunities=opportunities,
        opportunity_run_metadata=opportunity_run_metadata,
        load_warnings=warnings,
    )
