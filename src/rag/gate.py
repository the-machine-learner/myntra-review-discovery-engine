"""Similarity threshold gate and scope verification for Myntra RAG Chatbot."""

from __future__ import annotations

import os
import re

from src.config import RAG_SIMILARITY_THRESHOLD
from src.rag.retriever import RetrievedReview

REFUSAL_MESSAGE = (
    "Not enough signal in the reviews to answer that. "
    "Try rephrasing with Myntra categories, fresh items, refund complaints, or delivery habits."
)

OUT_OF_SCOPE_MESSAGE = (
    "Not enough signal in the reviews to answer that. "
    "This assistant only answers from Myntra review excerpts and user discussions, not general knowledge."
)

OUT_OF_SCOPE_PATTERN = re.compile(
    r"stock price|share price|market cap|\bCEO\b|aadit palicha|kaivalya vohra|"
    r"blinkit market share|instamart valuation|swiggy ipo|competitor|funding round|valuation",
    re.I,
)


def is_out_of_scope(question: str) -> bool:
    return bool(OUT_OF_SCOPE_PATTERN.search(question))


def max_similarity(retrieved: list[RetrievedReview]) -> float:
    if not retrieved:
        return 0.0
    return max(r.similarity for r in retrieved)


from src.config import RAG_SIMILARITY_THRESHOLD, get_secret


def passes_threshold(
    retrieved: list[RetrievedReview],
    threshold: float | None = None,
) -> bool:
    limit = threshold if threshold is not None else float(
        get_secret("RAG_SIMILARITY_THRESHOLD", str(RAG_SIMILARITY_THRESHOLD))
    )
    return max_similarity(retrieved) >= limit
