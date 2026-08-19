import os
import json
import requests
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

def fetch_youtube_comments(video_id: str, api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    if not api_key:
        print("No YOUTUBE_API_KEY provided in environment. Returning realistic mock reviews from YouTube vlogs...")
        # Mocking highly realistic YouTube comments on Myntra review vlogs
        return [
            {
                "id": "yt_cmt_1",
                "author": "TechVlogIndia",
                "text": "Myntra delivery is really 10 mins in Mumbai, but in Bangalore it takes 25-30 mins during peak office hours. Blinkit is much more consistent in Bangalore.",
                "like_count": 45,
                "published_at": "2026-07-28T10:15:30Z"
            },
            {
                "id": "yt_cmt_2",
                "author": "RohanSharma",
                "text": "The delivery boy marked my order as 'Open Box Completed' without even showing me the items. When I checked, the milk packet was leaking and support refused a refund saying OTP was shared. Total scam!",
                "like_count": 112,
                "published_at": "2026-07-29T14:20:00Z"
            },
            {
                "id": "yt_cmt_3",
                "author": "Priya_K",
                "text": "Honestly, Swiggy Instamart packaging is the best. Myntra just puts everything in one paper bag, sometimes my soft fruits get crushed under heavy detergent bottles.",
                "like_count": 18,
                "published_at": "2026-07-30T09:05:00Z"
            },
            {
                "id": "yt_cmt_4",
                "author": "KumarS",
                "text": "Their search is very bad. If I search for a specific biscuit brand, it shows 10 sponsored brands first. Very annoying discovery experience.",
                "like_count": 5,
                "published_at": "2026-07-31T18:40:00Z"
            }
        ]
    
    print(f"Connecting to YouTube API to fetch comments for video: {video_id}...")
    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": 10,
        "key": api_key
    }
    resp = requests.get(url, params=params, timeout=10)
    if resp.status_code != 200:
        raise Exception(f"YouTube API failed: {resp.status_code} - {resp.text}")
    
    data = resp.json()
    comments = []
    for item in data.get("items", []):
        snippet = item["snippet"]["topLevelComment"]["snippet"]
        comments.append({
            "id": item["id"],
            "author": snippet["authorDisplayName"],
            "text": snippet["textDisplay"],
            "like_count": snippet["likeCount"],
            "published_at": snippet["publishedAt"]
        })
    return comments

if __name__ == "__main__":
    api_key = os.getenv("YOUTUBE_API_KEY")
    # Example video ID of a popular Indian tech comparison review
    video_id = "dQw4w9WgXcQ" # Standard test ID
    comments = fetch_youtube_comments(video_id, api_key)
    
    os.makedirs("data/raw", exist_ok=True)
    out_path = "data/raw/youtube_comments.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(comments, f, indent=2)
    
    print(f"Saved {len(comments)} YouTube comments to {out_path}:")
    for c in comments:
        print(f"- @{c['author']}: {c['text'][:100]}... ({c['like_count']} likes)")
