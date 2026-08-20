from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from langdetect import LangDetectException, detect

from src.ingestion.schema import NormalizedReview


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    re.IGNORECASE,
)
PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"
)

_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


def scrub_pii(text: str) -> str:
    cleaned = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    cleaned = PHONE_PATTERN.sub("[REDACTED_PHONE]", cleaned)
    return cleaned


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text, flags=re.UNICODE))


def is_emoji_only(text: str) -> bool:
    stripped = _EMOJI_RE.sub("", text).strip()
    stripped = re.sub(r"[\s\W_]+", "", stripped, flags=re.UNICODE)
    return len(stripped) == 0


def normalize_body_key(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(collapsed.encode("utf-8")).hexdigest()


def is_english(text: str) -> bool:
    sample = text.strip()
    if len(sample) < 20:
        return True
    try:
        # Since quick commerce reviews often mix Hindi/English (Hinglish),
        # we tolerate simple/short inputs, but run detect for longer ones.
        return detect(sample) == "en"
    except LangDetectException:
        return False


# Cheap, zero-LLM-cost relevance gate for the wishlist-to-purchase-conversion
# research questions (fit/size, comparison, trust/quality, price/sale-waiting,
# availability, returns, styling, external validation, wishlist behavior
# itself). Only applied to noisy social-comment platforms (see
# TAXONOMY_FILTERED_PLATFORMS below) — app-store reviews are inherently
# on-topic (they're reviews of the Myntra app) and don't need this gate; a
# generic "great app 5 stars" review would otherwise get wrongly dropped.
TAXONOMY_RELEVANCE_PATTERN = re.compile(
    r"\b("
    r"wishlist|wish list|"
    r"size|fit|true to size|too (tight|loose|small|big)|"
    r"compar(e|ison)|\bvs\.?\b|versus|which (one|is better)|"
    r"fake|scam|fraud|duplicate|genuine|original|quality|trust|"
    r"sale|discount|price drop|wait(ing)? for|worth it|worth the (price|money)|expensive|cheap|"
    r"(out of )?stock|unavailable|available|"
    r"return|refund|exchange|replace(ment)?|"
    r"deliver(ed|y)|order(ed)?|received|"
    r"style|styling|occasion|outfit|pair (it |this )?with|wear|"
    r"recommend|suggest|honest review|opinion"
    r")\b",
    re.IGNORECASE,
)

# Platforms whose comments are social/reactive (haul-video comments, replies)
# rather than direct app reviews — these need the relevance gate above.
# App/Play Store reviews stay ungated since they're already on-topic by
# construction.
TAXONOMY_FILTERED_PLATFORMS = {"youtube", "x"}


def is_taxonomy_relevant(text: str) -> bool:
    return bool(TAXONOMY_RELEVANCE_PATTERN.search(text))


def normalize_reviews(
    raw_reviews: list[dict[str, Any]],
    min_word_count: int = 6,
    dedupe_window_hours: int = 24,
) -> tuple[list[NormalizedReview], Counter[str]]:
    stats: Counter[str] = Counter()
    kept: list[NormalizedReview] = []
    seen_keys: dict[str, datetime] = {}

    for raw in raw_reviews:
        stats["input_rows"] += 1
        body = str(raw.get("body") or "").strip()
        title = str(raw.get("title") or "").strip()
        platform = str(raw.get("platform", "google_play"))

        if is_emoji_only(body):
            stats["dropped_emoji_only"] += 1
            continue

        if word_count(body) < min_word_count:
            stats["dropped_too_short"] += 1
            continue

        if not is_english(body):
            stats["dropped_non_english"] += 1
            continue

        if platform in TAXONOMY_FILTERED_PLATFORMS and not is_taxonomy_relevant(body):
            stats["dropped_not_taxonomy_relevant"] += 1
            continue

        body = scrub_pii(body)
        title = scrub_pii(title)

        parsed_at = raw.get("_parsed_at")
        if not isinstance(parsed_at, datetime):
            parsed_at = datetime.fromisoformat(str(raw["date"]).replace("Z", "+00:00"))
        parsed_at = _ensure_utc(parsed_at)

        body_key = normalize_body_key(body)
        prior = seen_keys.get(body_key)
        if prior is not None:
            delta = abs((parsed_at - prior).total_seconds())
            if delta <= dedupe_window_hours * 3600:
                stats["dropped_duplicate"] += 1
                continue

        seen_keys[body_key] = parsed_at

        kept.append(
            NormalizedReview(
                review_id=str(raw["review_id"]),
                platform=str(raw.get("platform", "google_play")),
                date=str(raw["date"]),
                rating=int(raw["rating"]),
                title=title,
                body=body,
                app_version=str(raw.get("app_version") or ""),
                thumbs_up=int(raw.get("thumbs_up") or 0),
            )
        )

    stats["normalized_count"] = len(kept)
    return kept, stats


def date_range(reviews_list: list[NormalizedReview]) -> tuple[str | None, str | None]:
    if not reviews_list:
        return None, None
    dates = sorted(r.date for r in reviews_list)
    return dates[0], dates[-1]
