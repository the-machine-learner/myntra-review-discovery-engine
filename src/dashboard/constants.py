"""Dashboard constants and copy for the Myntra Wishlist Discovery Engine."""

from src.config import PROCESSED_DIR, PROJECT_ROOT

ARTIFACT_DIR = PROCESSED_DIR

LOGO_PATH = PROJECT_ROOT / "Myntra_logo_PNG_(2).png"

REVIEWS_FILE = "normalized_reviews.json"
OPPORTUNITY_SCORES_FILE = "opportunity_scores.json"
OPPORTUNITY_RUN_METADATA_FILE = "opportunity_run_metadata.json"
WISHLIST_SEGMENTS_FILE = "wishlist_segments.json"

MAX_SUMMARY_WORDS = 250

APP_TITLE = "Myntra Wishlist Discovery Engine"
APP_SUBTITLE = "Why wishlisted items don't convert to purchases — and which opportunities are worth acting on"
