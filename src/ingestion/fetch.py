from __future__ import annotations

import os
import json
import logging
import hashlib
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
    APIFY_API_TOKEN,
    APIFY_REDDIT_ACTOR_ID,
    APIFY_MAX_POSTS_PER_QUERY,
    APIFY_MAX_COMMENTS_PER_POST,
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

# --- 3. RESILIENT REDDIT CONNECTOR (3-TIER) ---
def _parse_reddit_post_dict(post_data: dict[str, Any], cutoff: datetime) -> list[dict[str, Any]]:
    """Flatten a Reddit post and its comments into individual review-like items."""
    results = []
    
    post_time = datetime.fromtimestamp(post_data.get("created_utc", datetime.now().timestamp()), timezone.utc)
    if post_time < cutoff:
        return results
        
    post_id = post_data["id"]
    title = post_data["title"]
    body = post_data.get("selftext", "").strip()
    subreddit = post_data.get("subreddit", "india")
    
    # OP Post
    if len(body) > 20: # Only include if it has actual text content
        results.append({
            "review_id": f"reddit_post_{post_id}",
            "platform": "reddit",
            "date": post_time.date().isoformat(),
            "rating": 3, # Neutral base rating
            "title": f"[{subreddit}] {title}",
            "body": body,
            "app_version": "",
            "thumbs_up": int(post_data.get("score", 0)),
            "_parsed_at": post_time,
        })
        
    # Process Comments
    comments = post_data.get("comments", [])
    for idx, comment in enumerate(comments):
        c_time = datetime.fromtimestamp(comment.get("created_utc", post_time.timestamp()), timezone.utc)
        c_body = comment.get("body", "").strip()
        c_author = comment.get("author", "anonymous")
        
        if len(c_body) > 15:
            results.append({
                "review_id": f"reddit_cmt_{post_id}_{idx}",
                "platform": "reddit",
                "date": c_time.date().isoformat(),
                "rating": 3,
                "title": f"Comment by u/{c_author} on: {title[:50]}...",
                "body": c_body,
                "app_version": "",
                "thumbs_up": int(comment.get("score", 0)),
                "_parsed_at": c_time,
            })
            
    return results

def fetch_reddit(lookback_weeks: int) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=lookback_weeks)
    collected = []
    seen_post_ids = set()
    
    client_id = os.getenv("REDDIT_CLIENT_ID", "")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
    
    queries = [
        # Why do users wishlist at all? (generic, not platform-anchored — people
        # rarely phrase this as a "myntra" search, it's a shopping-behavior post).
        # Short, Reddit-title-style phrasing — full-sentence queries were tested
        # and confirmed to underperform (Reddit search is keyword, not semantic).
        "myntra wishlist",
        "clothes wishlist",
        "saved items never buy",
        # What prevents a purchase / abandonment
        "abandoned cart",
        "buying from wishlist",
        # Uncertainty + postponing
        "should i buy this now",
        "myntra wait for sale",
        # Comparing multiple shortlisted products
        "which one should i buy",
        "can't decide outfit",
        # External validation-seeking (outside Myntra/Ajio)
        "rate my outfit",
        # Fit/size uncertainty
        "myntra size chart wrong",
        "myntra true to size",
        # Stock/variant availability friction
        "myntra size out of stock",
        "myntra color unavailable",
        # Trust/review-credibility
        "myntra fake reviews",
        "myntra scam",
        # Genuine intent vs. bookmarking + unmet needs
        "myntra wishlist saving for later",
        "myntra wish they had",
        "what i ordered vs what i got",
        "returned it the next day",
        "wishlist limit",
    ]

    # Strategy 1: PRAW (Preferred — official Reddit API, needs credentials)
    if client_id and client_secret:
        logger.info("Reddit Strategy 1: Attempting PRAW scraper with targeted queries")
        try:
            import praw
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=os.getenv("REDDIT_USER_AGENT", "macos:com.discoveryengine.scraper:v1.0.0 (by /u/prodkins)")
            )
            for q in queries:
                try:
                    for post in reddit.subreddit("all").search(q, sort="new", limit=10):
                        if post.id in seen_post_ids:
                            continue
                        seen_post_ids.add(post.id)
                        
                        post_data = {
                            "id": post.id,
                            "title": post.title,
                            "subreddit": post.subreddit.display_name,
                            "selftext": post.selftext,
                            "score": post.score,
                            "created_utc": post.created_utc,
                            "comments": []
                        }
                        post.comments.replace_more(limit=0)
                        for comment in post.comments[:5]:
                            post_data["comments"].append({
                                "author": str(comment.author),
                                "body": comment.body,
                                "score": comment.score,
                                "created_utc": comment.created_utc
                            })
                        collected.extend(_parse_reddit_post_dict(post_data, cutoff))
                except Exception as q_err:
                    logger.warning("PRAW failed for query '%s': %s", q, q_err)
            logger.info("Reddit PRAW fetch completed. Flattened items: %s", len(collected))
            if collected:
                return collected
        except Exception as e:
            logger.warning("Reddit PRAW scraper failed: %s. Trying Apify fallback.", e)

    # Strategy 2: Apify Reddit scraper (no Reddit login/API key needed)
    if APIFY_API_TOKEN:
        logger.info("Reddit Strategy 2: Attempting Apify Reddit scraper")
        try:
            apify_collected = fetch_reddit_via_apify(lookback_weeks, queries)
            logger.info("Apify Reddit fetch completed. Flattened items: %s", len(apify_collected))
            if apify_collected:
                return apify_collected
        except Exception as e:
            logger.warning("Apify Reddit scraper failed: %s. Falling back to local raw file.", e)

    # Final Fallback: local raw file
    reddit_path = RAW_DIR / "reddit_posts.json"
    if reddit_path.exists():
        with open(reddit_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for post_data in data:
                if post_data["id"] not in seen_post_ids:
                    seen_post_ids.add(post_data["id"])
                    collected.extend(_parse_reddit_post_dict(post_data, cutoff))
        logger.info("Loaded %s Reddit items from local snapshot.", len(collected))

    return collected


def _parse_apify_reddit_item(item: dict[str, Any], cutoff: datetime) -> dict[str, Any] | None:
    """Map one spry_wholemeal/reddit-scraper dataset item (post or comment) into
    a review-like dict, matching _parse_reddit_post_dict's shape/conventions.

    Field names confirmed against a real sample API response, not just the
    Actor's public docs (which were incomplete — e.g. undocumented `record_type`
    discriminator, and both record types carry a direct `post_id`, so no
    permalink-parsing is needed). Confirmed fields:
      post:    record_type, post_id, subreddit, title, text, author, score,
               is_self, created_utc_iso
      comment: record_type, post_id, comment_id, subreddit, text, author,
               score, created_utc_iso
    """
    record_type = item.get("record_type")
    if record_type not in ("post", "comment"):
        return None

    created_str = item.get("created_utc_iso")
    try:
        when = _ensure_utc(datetime.fromisoformat(str(created_str).replace("Z", "+00:00")))
    except (ValueError, TypeError):
        when = datetime.now(timezone.utc)
    if when < cutoff:
        return None

    body = str(item.get("text") or "").strip()
    author = item.get("author") or "anonymous"
    score = item.get("score") or 0
    subreddit = item.get("subreddit") or "reddit"
    post_id = item.get("post_id") or _generate_id(item.get("permalink") or body)

    if record_type == "comment":
        if len(body) <= 15:
            return None
        comment_id = item.get("comment_id") or _generate_id(item.get("permalink") or f"{author}{body}")
        return {
            "review_id": f"reddit_cmt_{post_id}_{comment_id}",
            "platform": "reddit",
            "date": when.date().isoformat(),
            "rating": 3,  # Neutral base rating — Reddit has no star rating
            "title": f"Comment by u/{author} in r/{subreddit}",
            "body": body,
            "app_version": "",
            "thumbs_up": int(score),
            "_parsed_at": when,
        }

    # Post record
    if len(body) <= 20:
        return None
    if not item.get("is_self", True) and body.startswith("submitted by /u/"):
        # Auto-generated crosspost/gallery/link-post blurb, not real user content
        return None
    title = item.get("title") or ""
    return {
        "review_id": f"reddit_post_{post_id}",
        "platform": "reddit",
        "date": when.date().isoformat(),
        "rating": 3,
        "title": f"[{subreddit}] {title}",
        "body": body,
        "app_version": "",
        "thumbs_up": int(score),
        "_parsed_at": when,
    }


def fetch_reddit_via_apify(lookback_weeks: int, queries: list[str]) -> list[dict[str, Any]]:
    """Fetch Reddit posts/comments via the Apify 'reddit-scraper' Actor
    (spry_wholemeal/reddit-scraper — pay-per-Apify-usage, no monthly rental).

    No Reddit login or API key required. Requires APIFY_API_TOKEN to be set —
    see .env.example. Costs Apify platform usage per run (compute/proxy/storage
    against your Apify account balance — see src/config.py caps).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=lookback_weeks)
    if lookback_weeks <= 1:
        timeframe = "week"
    elif lookback_weeks <= 4:
        timeframe = "month"
    elif lookback_weeks <= 52:
        timeframe = "year"
    else:
        timeframe = "all"

    # Apify's REST API path needs "username~actorName", not the Store's
    # human-facing "username/actorName" URL format.
    actor_path = APIFY_REDDIT_ACTOR_ID.replace("/", "~")
    url = f"https://api.apify.com/v2/acts/{actor_path}/run-sync-get-dataset-items"
    payload = {
        "mode": "search",
        "searchTargets": [{"query": q} for q in queries],
        "maxPosts": APIFY_MAX_POSTS_PER_QUERY,
        "sort": "new",
        "timeframe": timeframe,
        "includeCommentsMode": "all",
        "maxTopLevelComments": APIFY_MAX_COMMENTS_PER_POST,
    }

    response = requests.post(
        url,
        params={"token": APIFY_API_TOKEN},
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    items = response.json()

    collected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in items:
        parsed = _parse_apify_reddit_item(item, cutoff)
        if parsed and parsed["review_id"] not in seen_ids:
            seen_ids.add(parsed["review_id"])
            collected.append(parsed)
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
    
    if api_key:
        logger.info("YouTube Strategy: Attempting YouTube API search & fetch")
        video_ids = []
        try:
            search_url = "https://www.googleapis.com/youtube/v3/search"
            search_params = {
                "part": "snippet",
                "q": '"myntra app review" OR "myntra vs blinkit vs instamart"',
                "type": "video",
                "maxResults": 15,
                "relevanceLanguage": "en",
                "key": api_key
            }
            s_resp = requests.get(search_url, params=search_params, timeout=10)
            if s_resp.status_code == 200:
                s_data = s_resp.json()
                for item in s_data.get("items", []):
                    vid = item.get("id", {}).get("videoId")
                    if vid:
                        video_ids.append(vid)
                logger.info("YouTube search found videos: %s", video_ids)
            else:
                logger.warning("YouTube search API failed with status %s", s_resp.status_code)
        except Exception as e:
            logger.warning("YouTube search API call failed: %s", e)
            
        # Fallback to configured env IDs if search returned nothing
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
        active_sources = {"google_play", "app_store", "reddit", "x", "youtube"}
        
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
        
    # 3. Reddit
    if "reddit" in active_sources:
        rd_list = fetch_reddit(lookback_weeks)
        stats["raw_reddit"] = len(rd_list)
        all_reviews.extend(rd_list)
        
    # 4. X (Twitter)
    if "x" in active_sources or "twitter" in active_sources:
        x_list = fetch_x(lookback_weeks)
        stats["raw_x"] = len(x_list)
        all_reviews.extend(x_list)
        
    # 5. YouTube
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
