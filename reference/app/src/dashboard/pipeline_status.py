"""Pipeline freshness and status helper for Myntra VOC Engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.dashboard.constants import (
    ARTIFACT_DIR,
    REVIEWS_FILE,
    RUN_METADATA_FILE,
    THEMES_FILE,
)


@dataclass
class PipelineStatus:
    online: bool
    synced_label: str
    synced_local: str
    model_id: str
    review_count: int
    theme_count: int
    is_llm: bool
    run_id: str


def _file_mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _count_json_array(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return len(data) if isinstance(data, list) else 0
    except (OSError, json.JSONDecodeError):
        return 0


def get_pipeline_status() -> PipelineStatus:
    reviews_path = ARTIFACT_DIR / REVIEWS_FILE
    themes_path = ARTIFACT_DIR / THEMES_FILE
    meta_path = ARTIFACT_DIR / RUN_METADATA_FILE

    online = reviews_path.exists() and themes_path.exists()

    mtime = _file_mtime(themes_path) or _file_mtime(reviews_path)
    if mtime is not None:
        local = mtime.astimezone()
        synced_label = local.strftime("%I:%M %p").lstrip("0")
        synced_local = local.strftime("%b %d, %Y · %I:%M %p").lstrip("0")
    else:
        synced_label = "—"
        synced_local = "never"

    model_id = "—"
    run_id = "—"
    is_llm = False
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            model_id = str(meta.get("model_id", "—"))
            run_id = str(meta.get("run_id", "—"))
            is_llm = int(meta.get("groq_call_count", 0)) > 0
        except (OSError, json.JSONDecodeError):
            pass

    return PipelineStatus(
        online=online,
        synced_label=synced_label,
        synced_local=synced_local,
        model_id=model_id,
        review_count=_count_json_array(reviews_path),
        theme_count=_count_json_array(themes_path),
        is_llm=is_llm,
        run_id=run_id,
    )
