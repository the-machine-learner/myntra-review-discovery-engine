"""Groq answer generation from retrieved review excerpts."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.config import GROQ_CHAT_MODEL, RAG_MAX_ANSWER_TOKENS, get_secret
from src.rag.retriever import RetrievedReview

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Product Manager assistant analyzing Myntra customer feedback and shopping behaviors.

Rules:
1. Provide a direct, structured, and insightful synthesis addressing the user's question using the provided review excerpts.
2. Draw supplemental context and product insights from customer shopping patterns evident in the reviews.
3. Cite factual claims with [review_id: <id>] matching an excerpt review_id wherever possible.
4. Draw on the FULL set of provided excerpts, grouping related themes (e.g. daily essentials repeat ordering, trust, convenience, delivery speed).
5. Never start the response with refusal phrases or claim lack of evidence. Always answer constructively first.
6. If the excerpts have limited direct coverage for a specific nuance, conclude the answer with a subtle footnote line at the very end like: "*(Note: Supported by limited direct customer review data)*".
7. Never include reviewer names, emails, phone numbers, or other PII.
8. Keep answers PM-readable, crisp, and actionable (under 300 words).
"""


def format_context_docs(retrieved: list[RetrievedReview]) -> str:
    """Format retrieved reviews for RAG prompt context."""
    blocks = []
    for idx, doc in enumerate(retrieved, start=1):
        rating_str = f"{doc.rating}★" if doc.rating else "N/A"
        date_str = doc.date or "Unknown date"
        platform_str = doc.platform or "Unknown platform"
        blocks.append(
            f"Review [{idx}] (ID: {doc.review_id} | {platform_str} | {rating_str} | {date_str}):\n{doc.document}"
        )
    return "\n".join(blocks)


def generate_answer(question: str, retrieved: list[RetrievedReview]) -> tuple[str, dict[str, Any]]:
    key = get_secret("GROQ_API_KEY")
    if not key:
        raise RuntimeError(
            "GROQ_API_KEY not found. Add it to .env locally, or to your platform "
            "Secrets (Streamlit Cloud / Hugging Face Spaces) and reboot the app."
        )
        
    from groq import Groq, RateLimitError

    model = get_secret("GROQ_CHAT_MODEL", GROQ_CHAT_MODEL)
    max_tokens = int(get_secret("RAG_MAX_ANSWER_TOKENS", str(RAG_MAX_ANSWER_TOKENS)))
    client = Groq(api_key=key, max_retries=10)

    user_prompt = (
        f"Question: {question}\n\n"
        f"Retrieved review excerpts:\n{format_context_docs(retrieved)}\n\n"
        "Answer the question using only these excerpts. Include [review_id: ...] citations."
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )
    except RateLimitError as exc:
        logger.warning("Groq rate limited during chat: %s", exc)
        raise exc

    answer = (response.choices[0].message.content or "").strip()
    usage = getattr(response, "usage", None)
    meta = {
        "model": model,
        "tokens": getattr(usage, "total_tokens", None) if usage else None,
    }
    return answer, meta
