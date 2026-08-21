"""Fixed opportunity-area taxonomy for the wishlist-to-purchase-conversion
discovery engine.

Leaf module — no imports from src.embeddings or src.rag, since
src/embeddings/store.py imports from here (avoids circular imports).

Each OpportunityArea maps directly to one of the discovery-engine research
questions. `feasible_without_monetary_incentive` is a PM judgment call, seeded
once here — never LLM-derived — because that's the single biggest constraint
shaping which findings are actually actionable (no discounts allowed).
`mvp` controls whether an area is included in the first LLM-synthesis run;
flipping it is how Plan 3 Track A expands scope later without new code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

FeasibilityLevel = Literal["yes", "no", "partial"]


@dataclass(frozen=True)
class OpportunityArea:
    area_id: str
    label: str
    description: str
    keywords: tuple[str, ...]
    anchor_questions: tuple[str, ...]
    feasible_without_monetary_incentive: FeasibilityLevel
    mvp: bool


_AREAS: tuple[OpportunityArea, ...] = (
    # --- MVP (7) ---
    OpportunityArea(
        area_id="size_fit_uncertainty",
        label="Fit & Size Uncertainty",
        description=(
            "User is uncertain what size to order, unsure if an item will fit, "
            "or reports sizing not matching the chart/description."
        ),
        keywords=(
            "size chart", "true to size", "runs small", "runs large", "which size",
            "what size", "size doubt", "unsure about size", "returned for size",
            "size guide", "wrong size", "doesn't fit", "does not fit",
            "too tight", "too loose", "size unavailable in my", "fit issue",
        ),
        anchor_questions=(
            "What role does fit and size play in purchase hesitation?",
            "What uncertainties remain after a user has picked a product?",
        ),
        feasible_without_monetary_incentive="yes",
        mvp=True,
    ),
    OpportunityArea(
        area_id="comparison_paralysis",
        label="Comparison Paralysis",
        description=(
            "User has multiple similar shortlisted/wishlisted items and cannot "
            "decide between them."
        ),
        keywords=(
            # Tightened after finding "compare"/"comparison" matched generic
            # platform gripes ("compared to other platforms delivery is bad")
            # far more than genuine can't-decide-between-wishlisted-items
            # behavior (60 false / 2 true in cache before this change). All
            # phrases now anchor on "decide"/"choose"/"which one" so a bare
            # mention of comparing services no longer matches.
            "which one should i buy", "cant decide between", "can't decide between",
            "cant decide which", "can't decide which", "not sure which one to buy",
            "unsure which one to choose", "help me choose between", "help me decide between",
            "too many options to choose from", "confused which one to buy",
            "choose between these two", "decide between these two",
        ),
        anchor_questions=(
            "How do users compare multiple shortlisted products?",
            "What causes users to postpone a purchase?",
        ),
        feasible_without_monetary_incentive="yes",
        mvp=True,
    ),
    OpportunityArea(
        area_id="external_validation_seeking",
        label="External Validation-Seeking",
        description=(
            "User seeks opinions outside Myntra/Ajio before buying — friends, "
            "Instagram, YouTube, Reddit — or asks for others' opinions on a "
            "product before purchasing."
        ),
        keywords=(
            "asked my friends", "youtube review", "instagram", "influencer",
            "googled it", "rate my outfit", "honest review", "opinion",
            "should i buy", "recommend", "suggest",
        ),
        anchor_questions=(
            "What information do users seek outside Myntra/Ajio before purchasing?",
            "What role does social validation play in the purchase decision?",
        ),
        feasible_without_monetary_incentive="yes",
        mvp=True,
    ),
    OpportunityArea(
        area_id="wishlist_bookmark_no_intent",
        label="Wishlist as Bookmark, Not Intent",
        description=(
            "User treats the wishlist as a passive save/junk-drawer with no "
            "active purchase intent — items saved and forgotten, not tracked "
            "toward a purchase."
        ),
        keywords=(
            # Tightened after finding "forgot"/"no intention" matched
            # delivery/refund complaints ("no intention to give money back",
            # "forgot to implement the discounts") — 7 false / 0 true in
            # cache before this change. Every phrase now anchors on
            # save/wishlist + never-buy so a bare "forgot" elsewhere in a
            # review no longer matches.
            "just saving for later", "just browsing not buying", "wishlist just for looking",
            "no intention to buy it", "never intended to buy", "add to wishlist and forget",
            "forgot it was in my wishlist", "wishlist and never buy", "saved but never bought",
            "things i save but never buy", "wishlist pile up", "just window shopping",
        ),
        anchor_questions=(
            "When is the wishlist genuine purchase intent versus just a bookmark?",
            "Why do users add products to their wishlist?",
        ),
        feasible_without_monetary_incentive="yes",
        mvp=True,
    ),
    OpportunityArea(
        area_id="styling_occasion_uncertainty",
        label="Styling & Occasion Uncertainty",
        description=(
            "User is unsure how to style an item, whether it suits them, or "
            "whether it fits the occasion it was intended for."
        ),
        keywords=(
            # Tightened after finding "occasion"/"outfit"/"styling" matched
            # generic app praise ("suggests everything so perfectly and fits
            # my style") and unrelated order-for-an-occasion mentions — 36
            # false / 0 true in cache before this change. Every phrase now
            # requires an explicit uncertainty/negation signal (not sure,
            # unsure, will it, how do i) so bare fashion vocabulary no
            # longer matches on its own.
            "not sure how to style", "unsure how to style", "will it suit me",
            "not sure if it suits me", "what to wear it with", "how do i style this",
            "not sure what occasion to wear", "unsure what to pair it with",
            "how to pair this with", "not sure if this suits my body type",
        ),
        anchor_questions=(
            "What role does styling and occasion play in purchase hesitation?",
            "What uncertainties remain after a user has picked a product?",
        ),
        feasible_without_monetary_incentive="yes",
        mvp=True,
    ),
    OpportunityArea(
        area_id="stock_size_availability_friction",
        label="Stock / Size / Color Availability Friction",
        description=(
            "The specific size or color a user wants is out of stock or "
            "unavailable, including items that went out of stock while the "
            "user was deciding."
        ),
        keywords=(
            "out of stock", "size unavailable", "not available in my size",
            "sold out", "restock", "back in stock", "color unavailable",
            "not available in this color", "colour out of stock", "size not available",
        ),
        anchor_questions=(
            "What prevents wishlisted products from eventually being purchased?",
            "Does stock or size/color availability block a purchase?",
        ),
        feasible_without_monetary_incentive="yes",
        mvp=True,
    ),
    OpportunityArea(
        area_id="wishlist_price_watch",
        label="Wishlist as Price-Drop Watch",
        description=(
            "User wishlists an item specifically to monitor for a price drop or "
            "sale before buying — a price-anchored behavior, not a fit/trust "
            "concern."
        ),
        keywords=(
            "wait for sale", "price drop", "will buy when discount", "add and wait",
            "flash sale", "eors", "big billion", "waiting for price to drop",
            "hope it goes on sale", "wait for myntra sale", "worth it sale",
        ),
        anchor_questions=(
            "What causes users to postpone a purchase?",
            "Is the wishlist being used to track a price drop?",
        ),
        feasible_without_monetary_incentive="partial",
        mvp=True,
    ),
    # --- Deferred (7) — Plan 3 Track A ---
    OpportunityArea(
        area_id="price_general_hesitation",
        label="General Price Hesitation",
        description=(
            "Generic 'too expensive right now' hesitation not tied to a "
            "specific sale-watching behavior."
        ),
        keywords=(
            "expensive", "can't afford right now", "cant afford", "budget",
            "next salary", "too costly", "pricey",
        ),
        anchor_questions=("What causes users to postpone a purchase?",),
        feasible_without_monetary_incentive="no",
        mvp=True,
    ),
    OpportunityArea(
        area_id="wishlist_gift_list",
        label="Wishlist as Gift List",
        description="Item saved for a future gifting occasion, not near-term self-purchase.",
        keywords=(
            "gift", "birthday", "anniversary", "for my sister", "for my mom",
            "surprise", "rakhi", "diwali gift",
        ),
        anchor_questions=("Why do users add products to their wishlist?",),
        feasible_without_monetary_incentive="yes",
        mvp=True,
    ),
    OpportunityArea(
        area_id="wishlist_inspiration_board",
        label="Wishlist as Inspiration Board",
        description=(
            "Wishlist used as a mood/style board, not necessarily to buy the "
            "exact saved item."
        ),
        keywords=(
            "inspiration", "ideas", "outfit ideas", "reference", "style board",
            "mood board",
        ),
        anchor_questions=("Why do users add products to their wishlist?",),
        feasible_without_monetary_incentive="yes",
        mvp=True,
    ),
    OpportunityArea(
        area_id="trust_review_credibility_gap",
        label="Trust / Review Credibility Gap",
        description="User distrusts Myntra's on-platform reviews, photos, or authenticity claims.",
        keywords=(
            "fake reviews", "not as shown", "misleading photos", "no real reviews",
            "fake", "scam", "fraud", "duplicate", "genuine", "trust",
        ),
        anchor_questions=("What uncertainties remain after a user has picked a product?",),
        feasible_without_monetary_incentive="yes",
        mvp=True,
    ),
    OpportunityArea(
        area_id="quality_material_doubt",
        label="Quality / Material Doubt",
        description="Doubts about fabric/material/build quality relative to price.",
        keywords=(
            "quality", "material", "fabric", "cheap material", "not worth",
            "thin material", "poor quality", "material quality",
        ),
        anchor_questions=("What uncertainties remain after a user has picked a product?",),
        feasible_without_monetary_incentive="yes",
        mvp=True,
    ),
    OpportunityArea(
        area_id="return_exchange_anxiety",
        label="Return / Exchange Anxiety",
        description="Worry about return/exchange hassle discourages checkout, or a bad return experience.",
        keywords=(
            "return policy", "return hassle", "exchange issue", "no return",
            "restocking", "refund", "replacement", "difficult return",
        ),
        anchor_questions=("What prevents wishlisted products from eventually being purchased?",),
        feasible_without_monetary_incentive="yes",
        mvp=True,
    ),
    OpportunityArea(
        area_id="delivery_cod_payment_friction",
        label="Delivery / COD / Payment Friction",
        description="Delivery time, cash-on-delivery availability, or payment-method concerns block checkout.",
        keywords=(
            "cod not available", "payment failed", "delayed delivery", "no cod",
            "delivery delay", "late delivery",
        ),
        anchor_questions=("What prevents wishlisted products from eventually being purchased?",),
        feasible_without_monetary_incentive="yes",
        mvp=True,
    ),
)

TAXONOMY: dict[str, OpportunityArea] = {area.area_id: area for area in _AREAS}

MVP_AREA_IDS: tuple[str, ...] = tuple(a.area_id for a in _AREAS if a.mvp)

_COMPILED_PATTERNS: dict[str, re.Pattern[str]] = {
    area.area_id: re.compile(
        r"\b(" + "|".join(re.escape(kw) for kw in area.keywords) + r")\b",
        re.IGNORECASE,
    )
    for area in _AREAS
}


def classify_rule_based(body: str) -> list[str]:
    """Zero-cost regex match against ALL areas — runs on 100% of corpus,
    independent of which areas are in-scope for LLM synthesis this run."""
    if not body:
        return []
    return [area_id for area_id, pattern in _COMPILED_PATTERNS.items() if pattern.search(body)]
