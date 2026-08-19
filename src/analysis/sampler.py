"""Stratified sampling and heuristic tagging for Myntra feedback."""

from __future__ import annotations

import re
import random
from dataclasses import dataclass
from datetime import date
from typing import Any

from src.ingestion.schema import NormalizedReview

# Keywords associated with category discovery, exploration, shopping habits, or support frustrations
DISCOVERY_PATTERN = re.compile(
    r"explore|category|categories|discover|variety|option|habit|repeat|try|new|brand|selection|"
    r"search|recommend|suggest|organic|beauty|cosmetic|electronics|pet care|gourmet|item|find|"
    r"refund|open box|customer support|care|stuck|routine|same thing",
    re.IGNORECASE,
)

# Product discovery grievance & missing user needs pattern (450 review filter)
DISCOVERY_NEEDS_PATTERN = re.compile(
    r"missing|not found|absent|unavailable|out of stock|sold out|bring back|add category|wish you had|"
    r"need item|request|demand|brand absent|no option|no choice|limited choice|limited variety|few options|"
    r"less options|lack of options|bad recommendation|irritating|clogged|clutter|confusing|search fail|"
    r"poor search|broken search|bad search|cannot find|can't find|hard to discover|hard to find|"
    r"difficult to find|filter|filter useless|filter fail|wrong suggestion|wrong recommendation|irrelevant|"
    r"expiry|expiration|expiry date|ingredients|nutritional|weight missing|no details|substitute|alternative",
    re.IGNORECASE,
)

# Multi-category shoppers & platform comparison pattern (450 review filter)
MULTI_CATEGORY_PATTERN = re.compile(
    r"amazon|amazon fresh|bigbasket|bbnow|blinkit|instamart|swiggy|dunzo|flipkart|flipkart minutes|"
    r"other app|different app|another app|competing app|alternate app|local shop|local store|local vendor|"
    r"vendor|store|supermarket|kirana|mandi|offline store|multiple categories|different items|"
    r"groceries and|snacks and|beauty|cosmetic|medicine|pharmacy|electronics|switch|trust|cheaper|"
    r"price comparison|delivery charge|handling fee|platform fee",
    re.IGNORECASE,
)

SEGMENT_PATTERNS = {
    # 1. Household Replenisher: Family staples, groceries, cooking ingredients
    "household": re.compile(
        r"household|family|staples|grocery|groceries|vegetables|veggies|fruits|cook|cooking|oil|flour|rice|atta|milk|daily", 
        re.IGNORECASE
    ),
    # 2. Impulse Snackers & Night-Owls: Snacks, bachelors/students, late-night hours, cravings
    "impulse_night": re.compile(
        r"student|bachelor|single|flat|roommate|chips|coke|soda|beverage|snack|biscuits|chocolate|munchies|trial|night|midnight|late|1 am|2 am|3 am|1am|2am|3am|cravings", 
        re.IGNORECASE
    ),
    # 3. Hesitant Multi-Platformer: Alternate apps, trust issues, price complaints
    "multi_platformer": re.compile(
        r"amazon|bigbasket|blinkit|instamart|swiggy|other platform|other app|different app|local shop|vendor|cosmetic|beauty|trust|expiry|expensive|costly", 
        re.IGNORECASE
    ),
    # 4. Emergency & SOS Shoppers: Medicine, urgent, guests, cooking gaps
    "emergency_sos": re.compile(
        r"emergency|urgent|sos|medicine|pharmacy|cough|fever|medical|injury|band-aid|bandaid|guest|guests|cooking|need quickly", 
        re.IGNORECASE
    ),
    # 5. Premium / Gourmet Shopper: High value items, electronics, branded clothes, watches, expensive items
    "premium_gourmet": re.compile(
        r"electronics|gadget|charger|headphone|earbuds|watch|smartwatch|clothes|apparel|brand|branded|expensive|costly|premium|gourmet|imported|luxury|high end|high-end", 
        re.IGNORECASE
    ),
}

CELL_CAPS = {
    ("negative", True): 15,
    ("neutral", True): 8,
    ("positive", True): 5,
    ("negative", False): 3,
    ("neutral", False): 1,
    ("positive", False): 1,
}


@dataclass
class SampleResult:
    reviews: list[NormalizedReview]
    seed: int
    total_cap: int
    cell_counts: dict[str, int]


def iso_week(date_str: str) -> str:
    try:
        dt = date.fromisoformat(date_str)
        y, w, _ = dt.isocalendar()
        return f"{y}-W{w:02d}"
    except (ValueError, TypeError):
        return "unknown_week"


def rating_tier(rating: int) -> str:
    if rating <= 2:
        return "negative"
    if rating == 3:
        return "neutral"
    return "positive"


def is_discovery_candidate(body: str) -> bool:
    return bool(DISCOVERY_PATTERN.search(body))


def segment_hints(body: str) -> dict[str, bool]:
    return {k: bool(pat.search(body)) for k, pat in SEGMENT_PATTERNS.items()}


def stratified_sample(
    reviews: list[NormalizedReview],
    total_cap: int = 450,
    seed: int = 42,
) -> SampleResult:
    rng = random.Random(seed)
    buckets: dict[tuple[str, bool, str], list[NormalizedReview]] = {}

    for review in reviews:
        disc = is_discovery_candidate(review.body)
        tier = rating_tier(review.rating)
        week = iso_week(review.date)
        key = (tier, disc, week)
        buckets.setdefault(key, []).append(review)

    for items in buckets.values():
        rng.shuffle(items)

    selected: list[NormalizedReview] = []
    cell_counts: dict[str, int] = {}

    keys_sorted = sorted(
        buckets.keys(),
        key=lambda k: (
            0 if k[0] == "negative" and k[1] else 1 if k[1] else 2,
            k[2],
        ),
    )

    for tier, disc, week in keys_sorted:
        cap = CELL_CAPS.get((tier, disc), 1)
        pool = buckets[(tier, disc, week)]
        take = min(cap, len(pool))
        if take:
            chunk = pool[:take]
            selected.extend(chunk)
            label = f"{tier}|disc={disc}|{week}"
            cell_counts[label] = take

    rng.shuffle(selected)
    if len(selected) > total_cap:
        selected = selected[:total_cap]

    return SampleResult(
        reviews=selected,
        seed=seed,
        total_cap=total_cap,
        cell_counts=cell_counts,
    )


def discovery_subset(
    reviews: list[NormalizedReview],
    cap: int = 300,
) -> list[NormalizedReview]:
    scoped = [r for r in reviews if is_discovery_candidate(r.body)]
    if len(scoped) <= cap:
        return scoped
    return scoped[:cap]


DISCOVERY_NEEDS_KEYWORDS = [
    # Missing items & requests
    "missing", "not found", "absent", "unavailable", "out of stock", "sold out",
    "bring back", "add category", "wish you had", "need item", "request", "demand",
    "brand absent", "no option", "no choice", "limited choice", "limited variety",
    "few options", "less options", "lack of options", "less variety",
    # Search & filter friction
    "bad recommendation", "irritating", "clogged", "clutter", "confusing",
    "search fail", "poor search", "broken search", "bad search", "search useless",
    "cannot find", "can't find", "hard to discover", "hard to find", "difficult to find",
    "filter useless", "filter fail", "wrong suggestion", "wrong recommendation",
    "irrelevant", "irrelevant items",
    # Specs & information details
    "expiry", "expiration", "expiry date", "mfg date", "ingredients", "nutritional",
    "weight missing", "quantity missing", "no details", "substitute", "alternative", "replacement"
]

PLATFORM_KEYWORDS = [
    # Competitor apps
    "blinkit", "instamart", "bigbasket", "bbnow", "amazon", "amazon fresh",
    "flipkart", "flipkart minutes", "swiggy", "dunzo", "other app", "different app",
    "another app", "competing app", "alternate app", "myntra vs",
    # Offline & stores
    "local shop", "local store", "local vendor", "vendor", "supermarket", "kirana",
    "mandi", "offline store", "nearby shop", "retail store",
    # Price & fees
    "price comparison", "cheaper elsewhere", "cheaper on", "costly on", "expensive on",
    "delivery charge", "handling fee", "platform fee"
]

CATEGORY_KEYWORDS = [
    # Fresh & Staples
    "groceries", "grocery", "snacks", "munchies", "vegetables", "veggies", "fruits",
    "fresh produce", "dairy", "milk", "paneer", "curd", "butter", "cheese", "bread",
    "bakery", "staples", "atta", "rice", "oil", "dal", "pulses", "spices", "masala",
    "beverage", "beverages", "soda", "coke", "cold drink", "juice", "tea", "coffee", "water",
    # Personal Care & Beauty
    "beauty", "cosmetic", "cosmetics", "skincare", "haircare", "shampoo", "soap",
    "face wash", "sunscreen", "makeup", "lotion", "hygiene", "sanitary",
    # Health & Wellness
    "pharmacy", "medicine", "medicines", "otc", "supplements", "protein", "whey",
    "organic", "gluten free", "sugar free", "vegan", "wellness", "fitness", "gourmet", "imported",
    # Household & Others
    "cleaning", "detergent", "tissue", "pooja", "pet food", "pet care", "baby care",
    "diapers", "meat", "chicken", "fish", "eggs", "frozen", "ice cream", "chocolates",
    "sweets", "stationery", "electronics", "charger", "cable", "battery"
]


def _review_word_count(text: str) -> int:
    return len(text.split())


def user_needs_subset(
    reviews: list[NormalizedReview],
    cap: int = 450,
) -> list[NormalizedReview]:
    """Rank and extract top 450 reviews relevant to product discovery grievances using multi-feature scoring."""
    scored: list[tuple[float, NormalizedReview]] = []

    for r in reviews:
        body_lower = r.body.lower()
        
        # 1. Keyword density score
        match_count = sum(1 for kw in DISCOVERY_NEEDS_KEYWORDS if kw in body_lower)
        if match_count == 0:
            continue

        # 2. Length quality score (prefer informative reviews between 12 and 150 words)
        words = _review_word_count(r.body)
        length_score = 3.0 if 15 <= words <= 120 else (1.5 if 8 <= words < 15 else 0.5)

        # 3. Rating friction bonus (1★-3★ rating reviews contain richer friction details)
        friction_bonus = 2.5 if r.rating <= 2 else (1.5 if r.rating == 3 else 0.5)

        # 4. Helpfulness / Thumbs up bonus
        thumbs_bonus = min(r.thumbs_up or 0, 5) * 0.4

        total_score = (match_count * 3.0) + length_score + friction_bonus + thumbs_bonus
        scored.append((total_score, r))

    # Sort descending by score
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [r for _, r in scored[:cap]]

    if len(selected) < cap:
        # Fallback to general discovery candidate reviews if keyword matches are under cap
        existing_ids = {r.review_id for r in selected}
        for r in reviews:
            if r.review_id not in existing_ids and is_discovery_candidate(r.body):
                selected.append(r)
                if len(selected) >= cap:
                    break

    return selected[:cap]


def multi_category_subset(
    reviews: list[NormalizedReview],
    cap: int = 450,
) -> list[NormalizedReview]:
    """Rank and extract top 450 reviews relevant to multi-category shopping & platform comparison using multi-feature scoring."""
    scored: list[tuple[float, NormalizedReview]] = []

    for r in reviews:
        body_lower = r.body.lower()

        # 1. Competitor platform mentions
        platform_matches = sum(1 for kw in PLATFORM_KEYWORDS if kw in body_lower)

        # 2. Category domain mentions
        category_matches = sum(1 for kw in CATEGORY_KEYWORDS if kw in body_lower)

        if platform_matches == 0 and category_matches == 0:
            continue

        # 3. Cross-buying multiplier bonus if review mentions BOTH platforms and categories
        cross_bonus = 5.0 if (platform_matches > 0 and category_matches > 0) else 0.0

        # 4. Length score
        words = _review_word_count(r.body)
        length_score = 2.5 if 12 <= words <= 150 else 1.0

        # 5. Helpfulness bonus
        thumbs_bonus = min(r.thumbs_up or 0, 5) * 0.4

        total_score = (platform_matches * 2.5) + (category_matches * 2.0) + cross_bonus + length_score + thumbs_bonus
        scored.append((total_score, r))

    # Sort descending by score
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [r for _, r in scored[:cap]]

    if len(selected) < cap:
        existing_ids = {r.review_id for r in selected}
        for r in reviews:
            if r.review_id not in existing_ids and is_discovery_candidate(r.body):
                selected.append(r)
                if len(selected) >= cap:
                    break

    return selected[:cap]


