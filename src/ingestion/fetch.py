from __future__ import annotations

import os
import json
import logging
import hashlib
import re
import html
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from collections import Counter
from typing import Any

import requests
import urllib3
from google_play_scraper import Sort, reviews as play_reviews
from google_play_scraper.exceptions import NotFoundError

from src.config import PACKAGE_NAME, APP_STORE_ID, RAW_DIR, SERPAPI_API_KEY

logger = logging.getLogger(__name__)

# Suppress insecure request warnings for proxy verification
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Standard browser headers
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive'
}

USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

def _get_fresh_reddit_session() -> tuple[requests.Session, dict[str, str]]:
    import random
    session = requests.Session()
    ua = random.choice(USER_AGENTS)
    headers = {
        'User-Agent': ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0'
    }
    return session, headers

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
        "myntra refund OR open box",
        "myntra category OR discover OR options",
        "myntra beauty OR cosmetic OR personal care",
        "myntra pet food OR cat OR dog",
        "myntra baby OR diapers OR toys",
        "myntra vs blinkit OR instamart"
    ]
    
    # Strategy 1: PRAW (Preferred)
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
            logger.warning("Reddit PRAW scraper failed: %s. Trying legacy JSON/RSS.", e)

    # Strategy 2: SerpApi Google Reddit Search (Preferred key-free Reddit search)
    if SERPAPI_API_KEY:
        logger.info("Reddit Strategy 2: Attempting SerpApi Google Search for Reddit threads")
        try:
            import time
            import random
            serp_collected = []
            
            # We run 2 comprehensive queries to discover threads
            search_queries = [
                "site:reddit.com myntra app review OR feedback",
                "site:reddit.com myntra refund OR open box OTP OR fraud OR scam OR vs blinkit OR instamart"
            ]
            
            for sq in search_queries:
                params = {
                    "engine": "google",
                    "q": sq,
                    "api_key": SERPAPI_API_KEY,
                    "num": 20
                }
                logger.info("Querying SerpApi Google Search: %s", sq)
                response = requests.get("https://serpapi.com/search", params=params, timeout=15)
                if response.status_code != 200:
                    logger.warning("SerpApi Google Search failed with status %s", response.status_code)
                    continue
                    
                data = response.json()
                results = data.get("organic_results", [])
                logger.info("SerpApi found %s search results for query", len(results))
                
                for res in results:
                    link = res.get("link", "")
                    title = res.get("title", "Reddit Thread")
                    snippet = res.get("snippet", "").strip()
                    
                    if not link or "reddit.com" not in link:
                        continue
                        
                    # Extract post ID from link
                    post_id_match = re.search(r'/comments/([^/]+)/', link)
                    post_id = post_id_match.group(1) if post_id_match else _generate_id(link)
                    
                    if post_id in seen_post_ids:
                        continue
                    seen_post_ids.add(post_id)
                    
                    # Convert to RSS URL
                    thread_rss_url = link.split('?')[0].rstrip('/') + "/.rss"
                    
                    # Try to fetch RSS comments
                    rss_success = False
                    try:
                        # Sleep to respect WAF
                        time.sleep(random.uniform(2.0, 3.5))
                        session, headers = _get_fresh_reddit_session()
                        c_resp = session.get(thread_rss_url, headers=headers, timeout=6, verify=False)
                        if c_resp.status_code == 200:
                            root = ET.fromstring(c_resp.content)
                            ns = {'atom': 'http://www.w3.org/2005/Atom'}
                            entries = root.findall('atom:entry', ns)
                            
                            if entries:
                                # The first entry is the main post
                                op_entry = entries[0]
                                raw_content = op_entry.find('atom:content', ns).text or ""
                                clean_body = re.sub(r'<[^>]+>', '', html.unescape(raw_content))
                                
                                post_data = {
                                    "id": post_id,
                                    "title": title,
                                    "subreddit": "all",
                                    "selftext": clean_body if clean_body else snippet,
                                    "score": 5,
                                    "created_utc": datetime.now().timestamp(),
                                    "comments": []
                                }
                                
                                # Subsequent entries are comments
                                for c_entry in entries[1:8]:
                                    c_author = c_entry.find('atom:author/atom:name', ns)
                                    c_content = c_entry.find('atom:content', ns)
                                    if c_content is not None and c_content.text:
                                        c_body = re.sub(r'<[^>]+>', '', html.unescape(c_content.text))
                                        post_data["comments"].append({
                                            "author": c_author.text if c_author is not None else "anonymous",
                                            "body": c_body,
                                            "score": 2,
                                            "created_utc": datetime.now().timestamp()
                                        })
                                
                                parsed = _parse_reddit_post_dict(post_data, cutoff)
                                serp_collected.extend(parsed)
                                rss_success = True
                                logger.info("Successfully fetched thread RSS for %s (extracted %s items)", post_id, len(parsed))
                            else:
                                logger.warning("Empty RSS entries list for %s", post_id)
                        else:
                            logger.info("RSS fetch returned HTTP %s for %s. Falling back to snippet.", c_resp.status_code, post_id)
                    except Exception as rss_err:
                        logger.debug("Failed to fetch/parse RSS for thread %s: %s", post_id, rss_err)
                        
                    if not rss_success and len(snippet) > 20:
                        # Fallback: Add Google Search Snippet directly as OP Post
                        post_data = {
                            "id": post_id,
                            "title": title,
                            "subreddit": "all",
                            "selftext": snippet,
                            "score": 3,
                            "created_utc": datetime.now().timestamp(),
                            "comments": []
                        }
                        parsed = _parse_reddit_post_dict(post_data, cutoff)
                        serp_collected.extend(parsed)
                        logger.info("Added snippet fallback for %s", post_id)
                        
            if serp_collected:
                logger.info("SerpApi Reddit search completed. Flattened items: %s", len(serp_collected))
                return serp_collected
                
        except Exception as serp_err:
            logger.warning("SerpApi Google Search Strategy failed: %s. Trying legacy JSON/RSS.", serp_err)

    # Strategy 3: Public JSON Fallback
    logger.info("Reddit Strategy 2: Attempting Public JSON scraper with targeted queries using browser session rotation")
    try:
        import time
        import random
        json_collected = []
        for q in queries:
            session, headers = _get_fresh_reddit_session()
            escaped_q = urllib.parse.quote(q)
            url = f"https://www.reddit.com/search.json?q={escaped_q}&sort=new&limit=5"
            response = session.get(url, headers=headers, timeout=10, verify=False)
            if response.status_code == 200:
                data = response.json()
                posts = data.get("data", {}).get("children", [])
                for post_wrapper in posts:
                    post = post_wrapper.get("data", {})
                    if post["id"] in seen_post_ids:
                        continue
                    seen_post_ids.add(post["id"])
                    
                    post_data = {
                        "id": post["id"],
                        "title": post["title"],
                        "subreddit": post.get("subreddit", "india"),
                        "selftext": post.get("selftext", ""),
                        "score": post.get("score", 0),
                        "created_utc": post.get("created_utc", datetime.now().timestamp()),
                        "comments": []
                    }
                    comment_url = f"https://www.reddit.com{post['permalink']}.json?limit=5"
                    try:
                        c_session, c_headers = _get_fresh_reddit_session()
                        c_resp = c_session.get(comment_url, headers=c_headers, timeout=5, verify=False)
                        if c_resp.status_code == 200:
                            c_data = c_resp.json()
                            comments_list = c_data[1].get("data", {}).get("children", [])
                            for c_wrapper in comments_list:
                                c = c_wrapper.get("data", {})
                                if c.get("body"):
                                    post_data["comments"].append({
                                        "author": c.get("author", "anonymous"),
                                        "body": c.get("body", ""),
                                        "score": c.get("score", 0),
                                        "created_utc": c.get("created_utc", post["created_utc"])
                                    })
                    except Exception as c_err:
                        logger.debug("Failed to fetch comments for thread %s: %s", post["id"], c_err)
                    
                    json_collected.extend(_parse_reddit_post_dict(post_data, cutoff))
            else:
                logger.warning("Reddit Public JSON returned status %s for query %s", response.status_code, q)
            # Sleep between queries to avoid rate limits (respect WAF)
            time.sleep(random.uniform(1.5, 3.5))
            
        if json_collected:
            logger.info("Reddit Public JSON fetch completed. Flattened items: %s", len(json_collected))
            return json_collected
    except Exception as e:
        logger.warning("Reddit Public JSON failed: %s. Trying Public RSS/Atom.", e)

    # Strategy 3: Public RSS / Atom Fallback
    logger.info("Reddit Strategy 3: Attempting Public RSS/Atom scraper with targeted queries using browser session rotation")
    try:
        import time
        import random
        rss_collected = []
        for q in queries:
            session, headers = _get_fresh_reddit_session()
            escaped_q = urllib.parse.quote(q)
            url = f"https://www.reddit.com/search.rss?q={escaped_q}&sort=new"
            response = session.get(url, headers=headers, timeout=10, verify=False)
            
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                entries = root.findall('atom:entry', ns)
                
                for entry in entries:
                    post_id_match = re.search(r'/comments/([^/]+)/', entry.find('atom:link', ns).attrib.get('href', ''))
                    post_id = post_id_match.group(1) if post_id_match else _generate_id(entry.find('atom:title', ns).text)
                    
                    if post_id in seen_post_ids:
                        continue
                    seen_post_ids.add(post_id)
                    
                    title = entry.find('atom:title', ns).text or "Reddit Post"
                    author = entry.find('atom:author/atom:name', ns)
                    author_name = author.text if author is not None else "anonymous"
                    
                    raw_content = entry.find('atom:content', ns).text or ""
                    clean_body = re.sub(r'<[^>]+>', '', html.unescape(raw_content))
                    
                    post_data = {
                        "id": post_id,
                        "title": title,
                        "subreddit": "all",
                        "selftext": clean_body,
                        "score": 5,
                        "created_utc": datetime.now().timestamp(),
                        "comments": []
                    }
                    
                    thread_link = entry.find('atom:link', ns).attrib.get('href')
                    if thread_link:
                        thread_rss_url = thread_link.split('?')[0].rstrip('/') + "/.rss"
                        try:
                            comment_session, comment_headers = _get_fresh_reddit_session()
                            c_resp = comment_session.get(thread_rss_url, headers=comment_headers, timeout=5, verify=False)
                            if c_resp.status_code == 200:
                                c_root = ET.fromstring(c_resp.content)
                                c_entries = c_root.findall('atom:entry', ns)
                                for c_entry in c_entries[1:6]:
                                    c_author = c_entry.find('atom:author/atom:name', ns)
                                    c_content = c_entry.find('atom:content', ns)
                                    if c_content is not None and c_content.text:
                                        c_body = re.sub(r'<[^>]+>', '', html.unescape(c_content.text))
                                        post_data["comments"].append({
                                            "author": c_author.text if c_author is not None else "anonymous",
                                            "body": c_body,
                                            "score": 2,
                                            "created_utc": datetime.now().timestamp()
                                        })
                        except Exception as c_err:
                            logger.debug("Failed to fetch RSS comments for thread %s: %s", post_id, c_err)
                    
                    rss_collected.extend(_parse_reddit_post_dict(post_data, cutoff))
            else:
                logger.warning("Reddit RSS returned status %s for query %s", response.status_code, q)
            # Sleep between queries to avoid rate limits (respect WAF)
            time.sleep(random.uniform(1.5, 3.5))
            
        if rss_collected:
            logger.info("Reddit RSS fetch completed. Flattened items: %s", len(rss_collected))
            return rss_collected
    except Exception as e:
        logger.warning("Reddit RSS scraper failed: %s. Falling back to local raw file.", e)
        
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
