"""Groq answer generation from retrieved review excerpts. Ported from
reference/app/src/rag/generator.py — call shape unchanged, SYSTEM_PROMPT
rewritten for the wishlist-to-purchase-conversion domain (the old one was
grocery/quick-commerce-specific). Records actual token usage against the
shared Groq budget tracker (src/analysis/budget.py) after each successful
call, so batch and live chat draw from one coordinated daily budget.
"""

from __future__ import annotations

import logging
from typing import Any

from src.config import GROQ_CHAT_MODEL, RAG_MAX_ANSWER_TOKENS, get_secret
from src.rag.retriever import RetrievedReview
from src.analysis import budget

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Product Manager assistant analyzing Myntra/Ajio customer feedback about wishlist behavior and purchase decisions.

Rules:
1. Provide a direct, structured, and insightful synthesis addressing the user's question using the provided review excerpts.
2. Draw on themes evident in the reviews: fit/size uncertainty, styling/occasion doubt, comparison paralysis between similar items, price-drop/sale waiting, trust in reviews and product authenticity, stock/color/size availability, and whether the wishlist reflects genuine purchase intent or just passive bookmarking.
3. Cite factual claims with [review_id: <id>] matching an excerpt review_id wherever possible.
4. Draw on the FULL set of provided excerpts, grouping related themes rather than listing them one by one.
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
    total_tokens = getattr(usage, "total_tokens", None) if usage else None
    if total_tokens:
        budget.record_usage(int(total_tokens), calls=1)

    meta = {"model": model, "tokens": total_tokens}
    return answer, meta
