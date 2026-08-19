"""Dashboard constants and copy for Myntra VOC Engine."""

from pathlib import Path

from src.config import PROCESSED_DIR

ARTIFACT_DIR = PROCESSED_DIR
LKG_DIR = PROCESSED_DIR / "lkg"

THEMES_FILE = "themes.json"
UNMET_NEEDS_FILE = "unmet_needs.json"
SEGMENTS_FILE = "segments.json"
REVIEWS_FILE = "normalized_reviews.json"
RUN_METADATA_FILE = "run_metadata.json"

MAX_SUMMARY_WORDS = 250

SEGMENT_DISCLAIMER = (
    "How to read this: user segments are inferred from review wording using heuristics "
    "(e.g., mentions of milk/routine, specific brands, refund issues, or late-night snacks). "
    "These are qualitative indicators to guide product discovery, not rigid transactional metrics."
)

APP_TITLE = "Myntra VOC Analysis Engine"
APP_SUBTITLE = "Discovery engine for analysis on how customers discover new categories"
