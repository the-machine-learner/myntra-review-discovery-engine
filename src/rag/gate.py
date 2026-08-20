"""Similarity threshold gate and scope verification for the Myntra RAG
Chatbot. Ported from reference/app/src/rag/gate.py — the mechanism (regex
out-of-scope pre-filter + cosine-similarity floor before any generation call)
is unchanged; the out-of-scope terms and messages are rewritten for the
wishlist-to-purchase-conversion domain (the old ones targeted Zepto/quick-
commerce founders and competitors, not relevant here).
"""

from __future__ import annotations

import re

from src.config import RAG_SIMILARITY_THRESHOLD, get_secret
from src.rag.retriever import RetrievedReview

REFUSAL_MESSAGE = (
    "Not enough signal in the reviews to answer that. "
    "Try rephrasing around wishlist behavior, fit/size, comparison shopping, "
    "price-watching, trust in reviews, or return experiences."
)

OUT_OF_SCOPE_MESSAGE = (
    "Not enough signal in the reviews to answer that. "
    "This assistant only answers from Myntra/Ajio review excerpts and user "
    "discussions, not general knowledge or corporate/financial questions."
)

OUT_OF_SCOPE_PATTERN = re.compile(
    r"stock price|share price|market cap|\bCEO\b|\bIPO\b|funding round|valuation|"
    r"acquisition|flipkart earnings|reliance retail earnings|quarterly results|"
    r"revenue growth|profit margin|competitor market share",
    re.I,
)


def is_out_of_scope(question: str) -> bool:
    return bool(OUT_OF_SCOPE_PATTERN.search(question))


def max_similarity(retrieved: list[RetrievedReview]) -> float:
    if not retrieved:
        return 0.0
    return max(r.similarity for r in retrieved)


def passes_threshold(
    retrieved: list[RetrievedReview],
    threshold: float | None = None,
) -> bool:
    limit = threshold if threshold is not None else float(
        get_secret("RAG_SIMILARITY_THRESHOLD", str(RAG_SIMILARITY_THRESHOLD))
    )
    return max_similarity(retrieved) >= limit
