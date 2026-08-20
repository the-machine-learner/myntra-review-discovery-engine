from __future__ import annotations

import os
import json
import logging
import hashlib
import re
from datetime import datetime, timedelta, timezone
from collections import Counter
from typing import Any

import requests
from google_play_scraper import Sort, reviews as play_reviews
from google_play_scraper.exceptions import NotFoundError

from src.config import (
    PACKAGE_NAME,
    APP_STORE_ID,
    RAW_DIR,
    SERPAPI_API_KEY,
    MOUTHSHUT_PRODUCT_SLUG,
    MOUTHSHUT_MAX_PAGES,
)

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _generate_id(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]

# --- 1. GOOGLE PLAY FETCHER ---
def fetch_google_play(lookback_weeks: int) -> list[dict[str, Any]]:
    import time
    package = PACKAGE_NAME
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=lookback_weeks)
    collected = []
    
    logger.info("Attempting to fetch Google Play reviews for %s using token pagination", package)
    try:
        continuation_token = None
        target_count = 35000
        page_num = 1
        reached_cutoff = False
        
        while len(collected) < target_count and not reached_cutoff:
            logger.info("Fetching Google Play batch page %s (collected: %s/%s)...", page_num, len(collected), target_count)
            batch, continuation_token = play_reviews(
                package,
                lang='en',
                country='in',
                sort=Sort.NEWEST,
                count=120,
                continuation_token=continuation_token
            )
            
            if not batch:
                logger.info("No reviews returned in this Google Play batch. Ending loop.")
                break
                
            for raw in batch:
                at = _ensure_utc(raw.get("at"))
                if at < cutoff:
                    logger.info("Reached lookback cutoff review dated %s. Terminating pagination.", at.date().isoformat())
                    reached_cutoff = True
                    break
                    
                body = str(raw.get("content", "")).strip()
                if not body:
                    continue
                collected.append({
                    "review_id": str(raw.get("reviewId")),
                    "platform": "google_play",
                    "date": at.date().isoformat(),
                    "rating": int(raw.get("score", 0)),
                    "title": "",
                    "body": body,
                    "app_version": str(raw.get("reviewCreatedVersion") or ""),
                    "thumbs_up": int(raw.get("thumbsUpCount") or 0),
                    "_parsed_at": at,
                })
                
            page_num += 1
            if not continuation_token:
                logger.info("No continuation token returned by Google Play. Ending pagination.")
                break
                
            # Adhere to rate limits with a small sleep delay
            time.sleep(0.15)
            
        logger.info("Live Google Play fetch completed. Fetched %s raw reviews.", len(collected))
    except Exception as e:
        logger.warning("Google Play live fetch failed: %s. Falling back to local raw file.", e)
        # Fallback to local raw file
        play_path = RAW_DIR / "play_store_reviews.json"
        if play_path.exists():
            with open(play_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for raw in data:
                    # Parse date string
                    try:
                        at = _ensure_utc(datetime.strptime(raw["at"], "%Y-%m-%d %H:%M:%S"))
                    except (ValueError, KeyError):
                        at = datetime.now(timezone.utc)
                    collected.append({
                        "review_id": str(raw["reviewId"]),
                        "platform": "google_play",
                        "date": at.date().isoformat(),
                        "rating": int(raw["score"]),
                        "title": "",
                        "body": str(raw["content"]).strip(),
                        "app_version": str(raw.get("reviewCreatedVersion") or ""),
                        "thumbs_up": int(raw.get("thumbsUpCount") or 0),
                        "_parsed_at": at,
                    })
            logger.info("Loaded %s Google Play reviews from local snapshot.", len(collected))
    return collected

# --- 2. APPLE APP STORE FETCHER ---
def fetch_app_store(lookback_weeks: int) -> list[dict[str, Any]]:
    app_id = APP_STORE_ID
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=lookback_weeks)
    collected = []
    
    logger.info("Attempting to fetch Apple App Store reviews for ID %s using SerpApi", app_id)
    
    live_success = False
    if SERPAPI_API_KEY:
        try:
            page_num = 1
            max_pages = 10
            reached_cutoff = False
            
            while page_num <= max_pages and not reached_cutoff:
                params = {
                    "engine": "apple_reviews",
                    "product_id": str(app_id),
                    "api_key": SERPAPI_API_KEY,
                    "sort": "mostrecent",
                    "page": str(page_num)
                }
                
                logger.info("Fetching SerpApi page %s for product %s", page_num, app_id)
                response = requests.get("https://serpapi.com/search", params=params, timeout=15)
                
                if response.status_code != 200:
                    logger.warning("SerpApi returned HTTP status %s: %s", response.status_code, response.text)
                    break
                    
                data = response.json()
                reviews_list = data.get("reviews")
                if not reviews_list or not isinstance(reviews_list, list):
                    logger.info("No reviews or invalid reviews list in SerpApi response at page %s", page_num)
                    break
                
                logger.info("Found %s reviews on page %s", len(reviews_list), page_num)
                
                for rev in reviews_list:
                    content = (rev.get("text") or rev.get("title") or "").strip()
                    if not content:
                        continue
                        
                    date_str = rev.get("review_date")
                    if date_str:
                        try:
                            # Parse "Jun 02, 2021"
                            at = datetime.strptime(date_str, "%b %d, %Y").replace(tzinfo=timezone.utc)
                        except ValueError:
                            at = datetime.now(timezone.utc)
                    else:
                        at = datetime.now(timezone.utc)
                        
                    # Fetch all available reviews from App Store (no lookback cutoff)
                        
                    collected.append({
                        "review_id": str(rev.get("id") or _generate_id(content)),
                        "platform": "app_store",
                        "date": at.date().isoformat(),
                        "rating": int(rev.get("rating", 0)),
                        "title": rev.get("title", ""),
                        "body": content,
                        "app_version": rev.get("reviewed_version", ""),
                        "thumbs_up": 0,
                        "_parsed_at": at,
                    })
                
                # Check pagination
                pagination = data.get("serpapi_pagination", {})
                if "next" in pagination and not reached_cutoff:
                    page_num += 1
                else:
                    break
                    
            if len(collected) > 0:
                logger.info("SerpApi live App Store fetch completed. Fetched %s reviews.", len(collected))
                live_success = True
            else:
                logger.warning("SerpApi parsed 0 reviews within lookback period.")
                
        except Exception as e:
            logger.warning("SerpApi live App Store fetch failed: %s", e)
    else:
        logger.warning("SERPAPI_API_KEY not configured. Skipping live fetch.")
        
    if not live_success:
        logger.info("Falling back to local raw file for App Store reviews.")
        as_path = RAW_DIR / "app_store_reviews.json"
        if as_path.exists():
            with open(as_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for entry in data:
                    content = entry.get("content", {}).get("label", "").strip()
                    rating = int(entry.get("im:rating", {}).get("label", "0"))
                    rev_id = entry.get("id", {}).get("label", "")
                    version = entry.get("im:version", {}).get("label", "")
                    title = entry.get("title", {}).get("label", "")
                    
                    at = datetime.now(timezone.utc)
                    collected.append({
                        "review_id": str(rev_id or _generate_id(content)),
                        "platform": "app_store",
                        "date": at.date().isoformat(),
                        "rating": rating,
                        "title": title,
                        "body": content,
                        "app_version": version,
                        "thumbs_up": 0,
                        "_parsed_at": at,
                    })
            logger.info("Loaded %s App Store reviews from local snapshot.", len(collected))

    return collected


# --- 3. MOUTHSHUT FETCHER (needs a real browser — Cloudflare blocks curl/requests) ---
_MOUTHSHUT_RELATIVE_TIME_RE = re.compile(
    r"(\d+)\s*(hr|hrs|hour|hours|min|mins|minute|minutes|day|days|week|weeks|month|months|year|years)",
    re.IGNORECASE,
)
_MOUTHSHUT_UNIT_SECONDS = {
    "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "day": 86400, "days": 86400,
    "week": 604800, "weeks": 604800,
    "month": 2592000, "months": 2592000,  # 30-day approximation
    "year": 31536000, "years": 31536000,  # 365-day approximation
}


def _parse_mouthshut_date(date_text: str, scraped_at: datetime) -> datetime:
    """MouthShut mixes relative ("2 hrs 41 mins ago") and absolute
    ("Jul 20, 2026 03:40 PM") date formats on the same page. Relative dates
    are resolved against `scraped_at` (the time this page was fetched)."""
    text = date_text.strip()
    if "ago" in text.lower():
        total_seconds = 0
        for amount, unit in _MOUTHSHUT_RELATIVE_TIME_RE.findall(text):
            total_seconds += int(amount) * _MOUTHSHUT_UNIT_SECONDS.get(unit.lower(), 0)
        return scraped_at - timedelta(seconds=total_seconds)
    try:
        return _ensure_utc(datetime.strptime(text, "%b %d, %Y %I:%M %p"))
    except ValueError:
        return scraped_at


def _parse_mouthshut_review(article: Any, scraped_at: datetime, cutoff: datetime) -> dict[str, Any] | None:
    """Parse one .review-article BeautifulSoup element into a review-like dict."""
    title_el = article.select_one("strong a")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)
    url = title_el.get("href") or ""

    rating_span = article.select_one(".rating span")
    stars = len(rating_span.select("i.rated-star")) if rating_span else 0

    date_el = article.select_one("[id*=lblDateTime]")
    date_text = date_el.get_text(strip=True) if date_el else ""
    when = _parse_mouthshut_date(date_text, scraped_at) if date_text else scraped_at
    if when < cutoff:
        return None

    body_el = article.select_one(".reviewdata")
    body_paras = [p.get_text(strip=True) for p in body_el.find_all("p")] if body_el else []
    body = " ".join(p for p in body_paras if p).strip()
    if not body:
        return None

    review_id = _generate_id(url) if url else _generate_id(title + body)
    return {
        "review_id": f"mouthshut_{review_id}",
        "platform": "mouthshut",
        "date": when.date().isoformat(),
        "rating": stars or 3,
        "title": title,
        "body": body,
        "app_version": "",
        "thumbs_up": 0,
        "_parsed_at": when,
    }


def _mouthshut_launch_context(p: Any):
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )
    return browser, context


_MOUTHSHUT_PAGES_PER_BATCH = 4


def _mouthshut_load_page(page: Any, url: str, cutoff: datetime, BeautifulSoup: Any) -> list[Any]:
    """Navigate to `url`, wait for full render, return the review-article
    elements found. Raises on navigation failure.

    Uses "domcontentloaded", not "networkidle" — this site apparently never
    goes fully network-idle (background ads/analytics keep polling), which
    caused "networkidle" to hit 30s timeouts in testing. The fixed 6s
    wait_for_timeout after domcontentloaded is what actually lets Cloudflare's
    JS challenge settle.
    """
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    soup = BeautifulSoup(page.content(), "lxml")
    return soup.find_all(class_="review-article")


def fetch_mouthshut(lookback_weeks: int, max_pages: int | None = None) -> list[dict[str, Any]]:
    """Fetch Myntra reviews from MouthShut.com. Requires a real browser
    (Playwright + Chromium) — plain requests/curl get a Cloudflare 403.

    IMPORTANT — read before assuming this is reliable: four different access
    strategies were tried (sequential pagination, relaunching the browser
    every N pages, fully shuffled page order, and this one — priming with
    page 1 before every batch of new pages). Every single one of them BOTH
    succeeded in an isolated manual test AND failed on a real end-to-end run
    (pages beyond ~5 silently return duplicate content — still HTTP 200 with
    20 review-article elements, just reviews already seen, no error). That
    pattern — works in isolation, fails in practice, across every strategy —
    is strong evidence this is genuinely non-deterministic behavior on
    MouthShut/Cloudflare's side (likely rate- or randomization-based bot
    mitigation), not a client-side ordering puzzle with a real solution.

    This priming-batch strategy is kept as the implementation because it's
    the most defensible attempt and does no harm, but DO NOT expect it to
    reliably yield close to `max_pages` worth of content. In practice, expect
    roughly pages-1-5's worth (~80-100 reviews) most runs, occasionally more.
    The consecutive-empty/consecutive-all-duplicate safety valves below exist
    specifically so a bad run fails fast and cheap rather than burning
    through all of `max_pages` for nothing.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=lookback_weeks)
    max_pages = max_pages if max_pages is not None else MOUTHSHUT_MAX_PAGES
    collected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    try:
        from playwright.sync_api import sync_playwright
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning(
            "playwright/beautifulsoup4 not installed — skipping MouthShut "
            "(run `pip install playwright beautifulsoup4 lxml && playwright install chromium`)"
        )
        return collected

    base_url = f"https://www.mouthshut.com/product-reviews/{MOUTHSHUT_PRODUCT_SLUG}"
    target_pages = list(range(2, max_pages + 1))  # page 1's real content comes from the first priming visit
    batches = [
        target_pages[i : i + _MOUTHSHUT_PAGES_PER_BATCH]
        for i in range(0, len(target_pages), _MOUTHSHUT_PAGES_PER_BATCH)
    ]

    consecutive_empty = 0
    consecutive_all_dupe_batches = 0

    def _collect(articles: list[Any], scraped_at: datetime) -> int:
        new_count = 0
        for article in articles:
            parsed = _parse_mouthshut_review(article, scraped_at, cutoff)
            if parsed and parsed["review_id"] not in seen_ids:
                seen_ids.add(parsed["review_id"])
                collected.append(parsed)
                new_count += 1
        return new_count

    try:
        with sync_playwright() as p:
            browser, context = _mouthshut_launch_context(p)
            page = context.new_page()
            try:
                for batch in batches:
                    # Prime: (re)visit page 1 before every batch of new pages.
                    try:
                        articles = _mouthshut_load_page(page, base_url, cutoff, BeautifulSoup)
                        primed_new = _collect(articles, datetime.now(timezone.utc))
                        logger.info("MouthShut priming visit to page 1: %d articles, %d new", len(articles), primed_new)
                    except Exception as e:
                        logger.warning("MouthShut priming visit failed: %s", e)

                    batch_new = 0
                    batch_stopped = False
                    for page_num in batch:
                        url = f"{base_url}-page-{page_num}"
                        try:
                            articles = _mouthshut_load_page(page, url, cutoff, BeautifulSoup)
                        except Exception as e:
                            logger.warning("MouthShut page %d failed to load: %s", page_num, e)
                            continue

                        if not articles:
                            consecutive_empty += 1
                            logger.info(
                                "MouthShut page %d returned no reviews (%d consecutive empty)",
                                page_num, consecutive_empty,
                            )
                            if consecutive_empty >= 3:
                                logger.info("3 consecutive empty pages — stopping (likely past real content end).")
                                batch_stopped = True
                                break
                            continue
                        consecutive_empty = 0

                        page_new = _collect(articles, datetime.now(timezone.utc))
                        batch_new += page_new
                        logger.info(
                            "MouthShut page %d: %d reviews found, %d new after dedup/cutoff",
                            page_num, len(articles), page_new,
                        )

                    if batch_stopped:
                        break

                    if batch_new == 0:
                        consecutive_all_dupe_batches += 1
                        logger.info(
                            "MouthShut batch %s yielded zero new reviews (%d consecutive empty batches)",
                            batch, consecutive_all_dupe_batches,
                        )
                        if consecutive_all_dupe_batches >= 3:
                            logger.info("3 consecutive all-duplicate batches — stopping to avoid wasted requests.")
                            break
                    else:
                        consecutive_all_dupe_batches = 0
            finally:
                browser.close()
    except Exception as e:
        logger.warning("MouthShut fetch failed: %s", e)

    return collected


# --- 4. X (TWITTER) FETCHER ---
def fetch_x(lookback_weeks: int) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=lookback_weeks)
    collected = []
    
    # Live scraping X is blocked, so we only read from local JSON files
    x_path = RAW_DIR / "x_tweets.json"
    if x_path.exists():
        with open(x_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for tweet in data:
                try:
                    at = _ensure_utc(datetime.fromisoformat(tweet["created_at"]))
                except (ValueError, KeyError):
                    at = datetime.now(timezone.utc)
                if at < cutoff:
                    continue
                collected.append({
                    "review_id": f"x_{tweet['id']}",
                    "platform": "x",
                    "date": at.date().isoformat(),
                    "rating": 2, # Base rating for complaints
                    "title": f"Tweet by @{tweet['username']}",
                    "body": tweet["text"],
                    "app_version": "",
                    "thumbs_up": 0,
                    "_parsed_at": at,
                })
        logger.info("Loaded %s X tweets from local snapshot.", len(collected))
    return collected

# --- 4b. YOUTUBE COMMENT FETCHER ---
def fetch_youtube(lookback_weeks: int) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=lookback_weeks)
    collected = []

    api_key = os.getenv("YOUTUBE_API_KEY", "")

    # Queries phrased for YouTube's own video-title conventions (haul/vs/review/
    # "worth it" are common genre words), mapped to the wishlist-to-purchase
    # research questions. Each search.list call costs 100 quota units — 13
    # queries here is ~1,300 units/run, well within the 10,000/day free quota.
    queries = [
        # Wishlist / general shopping behavior (haul & declutter genre)
        "myntra haul",
        "myntra wishlist",
        "things i never wore haul",
        "clean out my closet things i never wore",
        # Postponing / sale-driven waiting
        "myntra sale haul",
        "is myntra sale worth it",
        # Comparison shopping
        "myntra vs ajio",
        "myntra vs ajio vs flipkart",
        # Fit/size uncertainty
        "myntra size review",
        "myntra true to size",
        # Trust/quality
        "myntra quality review",
        "myntra fake or real",
        # Buying-decision uncertainty
        "is myntra worth it",
        # Return experience
        "myntra return experience",
    ]

    if api_key:
        logger.info("YouTube Strategy: Attempting YouTube API search & fetch across %d queries", len(queries))
        video_ids: list[str] = []
        seen_video_ids: set[str] = set()
        search_url = "https://www.googleapis.com/youtube/v3/search"
        for q in queries:
            try:
                search_params = {
                    "part": "snippet",
                    "q": q,
                    "type": "video",
                    "maxResults": 10,
                    "relevanceLanguage": "en",
                    "key": api_key,
                }
                s_resp = requests.get(search_url, params=search_params, timeout=10)
                if s_resp.status_code == 200:
                    s_data = s_resp.json()
                    for item in s_data.get("items", []):
                        vid = item.get("id", {}).get("videoId")
                        if vid and vid not in seen_video_ids:
                            seen_video_ids.add(vid)
                            video_ids.append(vid)
                else:
                    logger.warning("YouTube search failed for query '%s': status %s", q, s_resp.status_code)
            except Exception as e:
                logger.warning("YouTube search API call failed for query '%s': %s", q, e)
        logger.info("YouTube search found %d unique videos across %d queries", len(video_ids), len(queries))

        # Fallback to configured env IDs if every search returned nothing
        if not video_ids:
            video_ids = os.getenv("YOUTUBE_VIDEO_IDS", "dQw4w9WgXcQ").split(",")

        for video_id in video_ids:
            video_id = video_id.strip()
            if not video_id:
                continue
            try:
                url = "https://www.googleapis.com/youtube/v3/commentThreads"
                params = {
                    "part": "snippet",
                    "videoId": video_id,
                    "maxResults": 50,
                    "key": api_key
                }
                resp = requests.get(url, params=params, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("items", []):
                        snippet = item["snippet"]["topLevelComment"]["snippet"]
                        try:
                            published_str = snippet["publishedAt"].replace("Z", "+00:00")
                            at = _ensure_utc(datetime.fromisoformat(published_str))
                        except (ValueError, KeyError):
                            at = datetime.now(timezone.utc)
                        if at < cutoff:
                            continue
                        collected.append({
                            "review_id": f"yt_{item['id']}",
                            "platform": "youtube",
                            "date": at.date().isoformat(),
                            "rating": 3,
                            "title": f"YouTube comment by @{snippet['authorDisplayName']}",
                            "body": snippet["textDisplay"],
                            "app_version": "",
                            "thumbs_up": int(snippet.get("likeCount", 0)),
                            "_parsed_at": at,
                        })
                else:
                    logger.warning("YouTube API failed for video %s: %s", video_id, resp.status_code)
            except Exception as e:
                logger.warning("YouTube API call failed: %s", e)
                
    if not collected:
        yt_path = RAW_DIR / "youtube_comments.json"
        if yt_path.exists():
            with open(yt_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for c in data:
                    try:
                        published_str = c["published_at"].replace("Z", "+00:00")
                        at = _ensure_utc(datetime.fromisoformat(published_str))
                    except (ValueError, KeyError):
                        at = datetime.now(timezone.utc)
                    if at < cutoff:
                        continue
                    collected.append({
                        "review_id": f"yt_{c['id']}",
                        "platform": "youtube",
                        "date": at.date().isoformat(),
                        "rating": 3,
                        "title": f"YouTube comment by @{c['author']}",
                        "body": c["text"],
                        "app_version": "",
                        "thumbs_up": int(c.get("like_count", 0)),
                        "_parsed_at": at,
                    })
            logger.info("Loaded %s YouTube comments from local snapshot.", len(collected))
            
    return collected

# --- 5. ORCHESTRATOR FETCH ---
def fetch_all(lookback_weeks: int, sources: list[str] | None = None) -> tuple[list[dict[str, Any]], Counter[str]]:
    stats = Counter()
    all_reviews = []
    
    # Standardize active sources list
    if sources:
        active_sources = {s.lower().strip() for s in sources}
    else:
        active_sources = {"google_play", "app_store", "x", "youtube"}

    # 1. Google Play
    if "google_play" in active_sources or "play_store" in active_sources:
        gp_list = fetch_google_play(lookback_weeks)
        stats["raw_google_play"] = len(gp_list)
        all_reviews.extend(gp_list)

    # 2. App Store
    if "app_store" in active_sources or "apple" in active_sources:
        as_list = fetch_app_store(lookback_weeks)
        stats["raw_app_store"] = len(as_list)
        all_reviews.extend(as_list)

    # 2b. MouthShut — opt-in only (not in the default set): needs a real
    # browser (Playwright+Chromium), meaningfully slower than the other
    # requests-based sources. Pass sources=["mouthshut", ...] explicitly.
    if "mouthshut" in active_sources:
        ms_list = fetch_mouthshut(lookback_weeks)
        stats["raw_mouthshut"] = len(ms_list)
        all_reviews.extend(ms_list)

    # 3. X (Twitter)
    if "x" in active_sources or "twitter" in active_sources:
        x_list = fetch_x(lookback_weeks)
        stats["raw_x"] = len(x_list)
        all_reviews.extend(x_list)

    # 4. YouTube
    if "youtube" in active_sources:
        yt_list = fetch_youtube(lookback_weeks)
        stats["raw_youtube"] = len(yt_list)
        all_reviews.extend(yt_list)
        
    stats["total_raw_fetched"] = len(all_reviews)
    return all_reviews, stats

def save_raw_snapshot(reviews_list: list[dict[str, Any]], path: str) -> None:
    import json
    from pathlib import Path

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    payload = [{k: v for k, v in r.items() if not k.startswith("_")} for r in reviews_list]
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
